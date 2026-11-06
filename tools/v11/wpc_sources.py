"""Retain primary documentation and optional canonical-tool retrieval outcomes."""
import urllib.request,re,json,traceback,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
def main():
    results=[]
    urls=['https://muhammad-asaduzzaman.github.io/projects/1_project/','https://muhammad-asaduzzaman.com/research/','https://asaduzzamanparvez.wordpress.com/software/','https://arxiv.org/html/2511.05205v1','https://software-lab.org/publications/icse2026_CodeMapper.pdf']
    for i,url in enumerate(urls):
        try:
            response=urllib.request.urlopen(url,timeout=45);raw=response.read();p=OUT/('primary-source-'+str(i)+('.pdf' if url.endswith('.pdf') else '.html'));p.write_bytes(raw)
            results.append(dict(url=url,status=response.status,path=str(p.relative_to(ROOT)),sha256=sha(p),archive_links=re.findall(r'href=[\"\']([^\"\']+(?:\.jar|\.zip)[^\"\']*)',raw.decode(errors='replace'))))
        except Exception as e:results.append(dict(url=url,error=repr(e)))
    write('primary-sources.json',results)
    write('canonical-lhdiff-attempts.json',dict(attempts=results[:3],status='No authoritative runnable download link obtained; existing tracker remains non-canonical',licence='No downloadable artifact licence established'))
if __name__=='__main__':main()
