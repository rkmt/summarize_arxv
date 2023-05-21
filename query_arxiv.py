import os
import io
import sys
import time
import arxiv
import openai
import random
from xml.dom import minidom
import xmltodict
import dicttoxml
import json

#OpenAIのapiキー
openai.api_key = 'your openai key'

prompt = """与えられた論文の要点をまとめ、以下の項目で日本語で出力せよ。それぞれの項目は最大でも180文字以内に要約せよ。
```
論文名:タイトルの日本語訳
キーワード:この論文のキーワード
課題:この論文が解決する課題
手法:この論文が提案する手法
結果:提案手法によって得られた結果
```"""

def get_summary(result):
    text = f"title: {result.title}\nbody: {result.summary}"
    print("### input text", text)
    #print("### input prompt", prompt)
    response = openai.ChatCompletion.create(
                #model="gpt-3.5-turbo",
                model='gpt-4',
                messages=[
                    {'role': 'system', 'content': prompt},
                    {'role': 'user', 'content': text}
                ],
                temperature=0.25,
            )
    summary = response['choices'][0]['message']['content']
    print("#### GPT", summary)
    dict = {}    
    for b in summary.split('\n'):
        print("****", b)
        if b.startswith("論文名"):
            dict['title_jp'] = b[4:].lstrip()
        if b.startswith("キーワード"):
            dict['keywords'] = b[6:].lstrip()
        if b.startswith("課題"):
            dict['problem'] = b[3:].lstrip()
        if b.startswith("手法"):
            dict['method'] = b[3:].lstrip()
        if b.startswith("結果"):
            dict['result'] = b[3:].lstrip()
    print("Dict by ChatGPT", dict)
    return dict

def get_paper_info(result, dirpath="./xmls"):
    dict = {}
    dict['title']= result.title
    dict['date'] = result.published.strftime("%Y-%m-%d %H:%M:%S")
    dict['authors'] = [x.name for x in result.authors]
    dict['year'] = str(result.published.year)
    dict['entry_id'] = str(result.entry_id)
    dict['primary_category'] = str(result.primary_category)
    dict['categories'] = result.categories
    dict['journal_ref'] = str(result.journal_ref)
    dict['pdf_url'] = str(result.pdf_url)
    dict['doi']= str(result.doi)
    dict['abstract'] = str(result.summary)
                
    print("##### DIR", dirpath, "PDF", result.pdf_url, "DOI", result.doi, "ID", id)
    if not os.path.exists(dirpath):
        os.mkdir(dirpath)

    # download paper PDF"
    print("download", f"{dirpath}/paper.pdf")
    result.download_pdf(dirpath=dirpath,filename="paper.pdf")
    dict['pdf'] = 'paper.pdf'

    # chatGPT summary
    dict2 = get_summary(result)

    root = {'paper': {**dict, **dict2}}
    return root

def main(query, dir='./xmls', num_papers=3, from_year=2017, max_results=100):
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    result_list = []
    for result in search.results():
        print(result, result.published.year, result.title)
        if result.published.year >= from_year:
            result_list.append(result)

    if len(result_list) <= 0:
        print("#### no result")
        sys.exit()
    
    if not os.path.exists(dir):  # make subfolder if necessary
        os.mkdir(dir)
    
    results = random.sample(result_list, k=num_papers) if num_papers > 0 and len(result_list) > num_papers else result_list

    for i, result in enumerate(results):
        try:
            id = result.entry_id.replace("http://", "").replace("/", "-")
            dirpath = f"{dir}/{id}"
            dict = get_paper_info(result, dirpath=dirpath)
            dict['paper']['query'] = query

            xml = dicttoxml.dicttoxml(dict, attr_type=False, root=False).decode('utf-8')
            xml = minidom.parseString(xml).toprettyxml(indent="   ")
            print("###########\n", xml, "\n#######")

            with open(f"{dirpath}/paper.xml", "w") as f:
                f.write(xml)
        except Exception as e:
            print("Exception", e)

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', '-y', type=int, help='from year', default=2017)
    parser.add_argument('--dir', "-d", type=str, help='destination', default='./xmls')
    parser.add_argument('--num', "-n", type=int, help='number of papers', default=0)    
    parser.add_argument('positional_args', nargs='+', help='query keywords')
    args = parser.parse_args()

    print(args)

    main(query=f'all:%22 {" ".join(args.positional_args)} %22', num_papers=args.num, from_year=args.year, dir=args.dir)

