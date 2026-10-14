import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const dom=new JSDOM('<!doctype html><html><body></body></html>');
globalThis.window=dom.window;
globalThis.document=dom.window.document;
globalThis.DOMParser=dom.window.DOMParser;
const {default:mermaid}=await import('mermaid');
mermaid.initialize({startOnLoad:false,securityLevel:'strict'});
const files=execFileSync('git',['ls-files','-z'],{encoding:'utf8'}).split('\0')
  .filter(file=>file==='README.md'||(file.startsWith('docs/')&&file.endsWith('.md')));
let count=0;
for(const file of files){
  for(const block of readFileSync(file,'utf8').matchAll(/```mermaid\s*\n([\s\S]*?)```/g)){
    try{await mermaid.parse(block[1]);count++;}
    catch(error){throw new Error(`MERMAID_PARSE_FAILED ${file}: ${error.message}`);}
  }
}
console.log(`MERMAID_DIAGRAMS_VERIFIED ${count}`);
