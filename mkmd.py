import os
import io
import sys
import time
import arxiv
import openai
import random
import fitz
from xml.dom import minidom
import xmltodict
import dicttoxml
import json
import glob
import xmltodict
from PIL import Image

print(fitz.__doc__)

if not tuple(map(int, fitz.version[0].split("."))) >= (1, 18, 18):
    raise SystemExit("require PyMuPDF v1.18.18+")

def recoverpix(doc, item):
    xref = item[0]  # xref of PDF image
    smask = item[1]  # xref of its /SMask

    # special case: /SMask or /Mask exists
    if smask > 0:
        pix0 = fitz.Pixmap(doc.extract_image(xref)["image"])
        if pix0.alpha:  # catch irregular situation
            pix0 = fitz.Pixmap(pix0, 0)  # remove alpha channel
        mask = fitz.Pixmap(doc.extract_image(smask)["image"])

        try:
            pix = fitz.Pixmap(pix0, mask)
        except:  # fallback to original base image in case of problems
            pix = fitz.Pixmap(doc.extract_image(xref)["image"])

        if pix0.n > 3:
            ext = "pam"
        else:
            ext = "png"

        return {  # create dictionary expected by caller
            "ext": ext,
            "colorspace": pix.colorspace.n,
            "image": pix.tobytes(ext),
        }

    # special case: /ColorSpace definition exists
    # to be sure, we convert these cases to RGB PNG images
    if "/ColorSpace" in doc.xref_object(xref, compressed=True):
        pix = fitz.Pixmap(doc, xref)
        pix = fitz.Pixmap(fitz.csRGB, pix)
        return {  # create dictionary expected by caller
            "ext": "png",
            "colorspace": 3,
            "image": pix.tobytes("png"),
        }
    return doc.extract_image(xref)


def extract_images_from_pdf(fname, imgdir="./output", min_width=400, min_height=400, relsize=0.05, abssize=2048, max_ratio=8, max_num=5):
    '''
    dimlimit = 0  # 100  # each image side must be greater than this
    relsize = 0  # 0.05  # image : image size ratio must be larger than this (5%)
    abssize = 0  # 2048  # absolute image size limit 2 KB: ignore if smaller
    '''

    if not os.path.exists(imgdir):  # make subfolder if necessary
        os.mkdir(imgdir)

    t0 = time.time()
    doc = fitz.open(fname)
    page_count = doc.page_count  # number of pages

    xreflist = []
    imglist = []
    images = []
    for pno in range(page_count):
        if len(images) >= max_num:
            break
        print(f"extract images {pno+1}/{page_count}")
        il = doc.get_page_images(pno)
        imglist.extend([x[0] for x in il])
        for img in il:
            xref = img[0]
            if xref in xreflist:
                continue
            width = img[2]
            height = img[3]
            print(f"{width}x{height}")
            if width < min_width and height < min_height:
                continue
            image = recoverpix(doc, img)
            n = image["colorspace"]
            imgdata = image["image"]

            if len(imgdata) <= abssize:
                continue

            if width / height > max_ratio or height/width > max_ratio:
                print(f"max_ration {width/height} {height/width} {max_ratio}")
                continue

            print("*")

            imgname = "img%02d_%05i.%s" % (pno+1, xref, image["ext"])
            images.append((imgname, pno+1, width, height))
            imgfile = os.path.join(imgdir,  imgname)
            fout = open(imgfile, "wb")
            fout.write(imgdata)
            fout.close()
            xreflist.append(xref)

    t1 = time.time()
    imglist = list(set(imglist))
    print(len(set(imglist)), "images in total")
    print(len(xreflist), "images extracted")
    print("total time %g sec" % (t1 - t0))
    return xreflist, imglist, images

def get_half(fname):
    # Open the PDF file
    pdf_file = fitz.open(fname)
    # Get the first page
    page = pdf_file[0]
    # Get the page as a whole image
    mat = fitz.Matrix(2, 2)  # zoom factor 2 in each direction
    pix = page.get_pixmap(matrix=mat)
    # Convert to a PIL Image
    im = Image.open(io.BytesIO(pix.tobytes()))
    # Get the dimensions of the image
    width, height = im.size
    # Define the box for the upper half (left, upper, right, lower)
    box = (0, height // 20, width, (height // 2) + (height // 20))

    # Crop the image to this box
    im_cropped = im.crop(box)
    return im_cropped



def make_md(f, dirname, filename, nimages=3, keywords=[]):
    path = f"{dirname}/{filename}"
    with open(path, "r") as fin:
        xml = fin.read()
        xml_lower = xml.lower()
        if (keywords is not None) and not(any([k.lower() in xml_lower for k in keywords])):
            return
    dict = xmltodict.parse(xml)['paper']
    print(dict)
    f.write('\n---\n')
    f.write('<!-- _class: title -->\n')
    f.write(f"# {dict['title_jp']}\n")
    f.write(f"{dict['title']}\n")
    #authors = ",".join(dict['authors']['item'])
    #f.write(f"{authors}\n")
    f.write(f"[{dict['year']}] {dict['keywords']} {dict['entry_id']}\n") 
    f.write(f"__課題__ {dict['problem']}\n")
    f.write(f"__手法__ {dict['method']}\n")
    f.write(f"__結果__ {dict['result']}\n")

    pdfname = f"{dirname}/paper.pdf"
    img_cropped = get_half(pdfname)
    img_cropped.save(f"{dirname}/half.png", "PNG")
    
    f.write("\n---\n")
    f.write('<!-- _class: info -->\n') 
    f.write(f'![width:1400]({dirname}/half.png)\n')

    # get images
    _, _, image_list = extract_images_from_pdf(pdfname, imgdir=dirname)
    images = [{'src':imgname, 'pno':str(pno), 'width':str(width), 'height':str(height)} for imgname, pno, width, height in image_list]
    for img in images[:nimages]:
        src = img['src']
        width = (int)(img['width'])
        height = (int)(img['height'])
        print("#### img", src, width, height)
        x_ratio = (1600.0 * 0.7) / (float)(width)
        y_ratio = (900.0 * 0.7) / (float)(height)
        ratio = min(x_ratio, y_ratio)

        f.write("\n---\n")
        f.write('<!-- _class: info -->\n') 
        f.write(f'![width:{(int)(ratio * width)}]({dirname}/{src})\n')

def main(dir="./xmrs", output="./out.md", keywords=[]):
    print("### dir", dir, "output", output, "keywords", keywords)
    xmlfiles= glob.glob(f"{dir}/*/*.xml")
    with open(output, "w") as f:
        f.write("---\n")
        f.write("marp: true\n")
        f.write("theme: default\n")
        f.write("size: 16:9\n")
        f.write("paginate: true\n")
        f.write('_class: ["cool-theme"]\n')
        f.write('\n---\n')
        f.write(f'# {keywords} on arXiv\n')
        f.write('automatically generated by ChatGPT\n')
        f.write('\n')

        for file in xmlfiles:
            dirname, filename = os.path.split(file)
            print(dirname, filename)
            make_md(f, dirname, filename, keywords=keywords)
    print("### result stored in", output)

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', "-d", type=str, help='xml dir', default='./xmls')
    parser.add_argument('--output', "-o", type=str, default='output.md', help='output markdown file')
    parser.add_argument('positional_args', nargs='?', help='query keywords')
    args = parser.parse_args()

    keywords = args.positional_args
    if type(keywords) == str:
        keywords = [keywords]

    print(args, keywords)
    
    main(dir=args.dir, output=args.output, keywords=keywords)