from pathlib import Path
import re,json
P=Path(__file__).resolve().parent
src=(P/'oltp_snapshot_schema.sql').read_text()
# Keep structural SQL only: no source data, credentials, sequence state or connection options.
def blocks(s):
 s=re.sub(r'--[^\n]*','',s)
 return re.findall(r'CREATE TABLE(?: IF NOT EXISTS)?\s+([\w.]+)\s*\((.*?)\)\s*(?:PARTITION BY RANGE\s*\([^)]*\))?\s*;',s,re.S)
for kind, source in [('oltp',src),('dw','\n'.join(p.read_text() for p in sorted(Path('dw/sql/30_dw').glob('*.sql'))))]:
 out=[]
 for name,body in blocks(source):
  body=re.sub(r"\s+DEFAULT nextval\('[^']+'::regclass\)",'',body)
  out.append(f'CREATE TABLE {name} (\n{body.strip()}\n);')
 if kind=='oltp':
  out+=re.findall(r'ALTER TABLE ONLY\s+[\w.]+\s+ADD CONSTRAINT\s+\w+\s+(?:PRIMARY KEY|UNIQUE|FOREIGN KEY).*?;',source,re.S)
 (P/f'{kind}_drawsql.sql').write_text('\n\n'.join(out)+'\n')
 print(kind,len(blocks(source)),'tables',len('\n'.join(out)),'chars')
