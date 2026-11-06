"""Extract the published tables from the retained primary HTML, not hand numbers."""
from html.parser import HTMLParser
import sys,re,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
class Tables(HTMLParser):
    def __init__(self):super().__init__();self.tables=[];self.table=None;self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':self.table=[]
        if self.table is not None and tag=='tr':self.row=[]
        if self.row is not None and tag in ('td','th'):self.cell=[]
    def handle_data(self,text):
        if self.cell is not None:self.cell.append(text)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(re.sub(r'\s+',' ',''.join(self.cell)).strip());self.cell=None
        if tag=='tr' and self.row is not None:self.table.append(self.row);self.row=None
        if tag=='table' and self.table is not None:self.tables.append(self.table);self.table=None
def main():
    p=Tables();p.feed((OUT/'primary-source-3.html').read_text(encoding='utf-8'))
    chosen=[t for t in p.tables if any(r and r[0]=='Exact matches' for r in t)]
    write('published-tables.json',chosen,[OUT/'primary-source-3.html'])
    for t in chosen:print(json.dumps(t,ensure_ascii=False))
if __name__=='__main__':main()
