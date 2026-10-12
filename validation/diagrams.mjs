import { JSDOM } from 'jsdom';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

const dom=new JSDOM('<!doctype html><html><body></body></html>');
globalThis.window=dom.window;
globalThis.document=dom.window.document;
globalThis.DOMParser=dom.window.DOMParser;
const {default:mermaid}=await import('mermaid');
mermaid.initialize({startOnLoad:false,securityLevel:'strict'});
function files(directory){
  return readdirSync(directory,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()
    ?files(path.join(directory,entry.name)):[path.join(directory,entry.name)]);
}
let count=0;
for(const file of ['README.md',...files('docs')].filter(file=>file.endsWith('.md'))){
  // Only tracked documentation: the private, untracked handoff is not uploaded.
  if(file.endsWith('handoff-2026-10-12-k3s-ready.md'))continue;
  for(const block of readFileSync(file,'utf8').matchAll(/```mermaid\s*\n([\s\S]*?)```/g)){
    try{await mermaid.parse(block[1]);count++;}
    catch(error){throw new Error(`MERMAID_PARSE_FAILED ${file}: ${error.message}`);}
  }
}
console.log(`MERMAID_DIAGRAMS_VERIFIED ${count}`);
