"""Local-only DLP preview. No function in this module authorizes cloud export."""
import hashlib
import hmac
import json
import re
import unicodedata

MAX_TEXT=100000
TOKEN=re.compile(r'\[ARCIA_[A-Z_]+_[a-f0-9]{20}\]|\[SECRET_REMOVED\]')
SECRETS=[
    re.compile(r'-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----[\s\S]*?-----END (?:[A-Z ]*PRIVATE KEY)-----'),
    re.compile(r'(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|authorization|mot[ _]de[ _]passe)\s*[:=]\s*["\']?[^\s,"\'};]{3,}'),
    re.compile(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b'),
    re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}')]
TECHNICAL=[
    ('IP',re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?(?![\w.])')),
    ('IP',re.compile(r'(?<!\w)(?:[a-fA-F0-9]{0,4}:){2,}[a-fA-F0-9:]{0,39}(?!\w)')),
    ('MAC',re.compile(r'\b(?:[a-fA-F0-9]{2}[:-]){5}[a-fA-F0-9]{2}\b')),
    ('ID',re.compile(r'\b[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}\b')),
    ('HOST',re.compile(r'(?i)\b[a-z0-9](?:[a-z0-9_-]*\.)+[a-z][a-z0-9-]{1,62}\b')),
    ('HOST',re.compile(r'(?i)\b(?:esxi|vcenter|vcsa|srv|server|fw|switch|router|db|sql)[-_][a-z0-9_-]+\b')),
    ('EMAIL',re.compile(r'(?i)[\w.+-]+@[\w.-]+\.[a-z]{2,}')),
    ('PHONE',re.compile(r'(?<!\d)(?:\+33|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)'))]


class Blocked(ValueError):pass


class Sanitizer:
    def __init__(self,analyzer,key,scope,identifiers=()):
        if len(key)<32 or not scope:raise Blocked('INVALID_SERVER_POLICY')
        self.analyzer=analyzer;self.key=key;self.scope=scope
        self.identifiers=tuple(unicodedata.normalize('NFKC',s).casefold() for s in identifiers if s)

    def text(self,text):
        if not isinstance(text,str) or len(text)>MAX_TEXT:raise Blocked('TEXT_REQUIRED_OR_TOO_LARGE')
        text=unicodedata.normalize('NFKC',text)
        text=''.join(c for c in text if unicodedata.category(c)!='Cf')
        if not text:return '',{}
        if any(ord(c)<32 and c not in '\n\r\t' for c in text):raise Blocked('OPAQUE_CONTROL_DATA')
        if re.search(r'(?i)data:|-----BEGIN (?![A-Z ]*PRIVATE KEY)|\b[A-Za-z0-9+/]{100,}={0,2}',text):raise Blocked('OPAQUE_OR_ENCODED_DATA')
        spans=[]
        for pattern in SECRETS:
            spans.extend((m.start(),m.end(),'SECRET') for m in pattern.finditer(text))
        for kind,pattern in TECHNICAL:
            spans.extend((m.start(),m.end(),kind) for m in pattern.finditer(text))
        for identifier in self.identifiers:
            spans.extend((m.start(),m.end(),'PRIVATE') for m in re.finditer(re.escape(identifier),text,re.I))
        # Analyze both languages; a caller cannot bypass a detector via a flag.
        for language in ('fr','en'):
            results=self.analyzer.analyze(text=text,language=language,score_threshold=.2)
            spans.extend((r.start,r.end,r.entity_type) for r in results)
        merged=[]
        for start,end,kind in sorted(spans):
            if not (0<=start<end<=len(text)):raise Blocked('DETECTOR_RANGE_INVALID')
            if merged and start<merged[-1][1]:
                a,b,k=merged[-1];merged[-1]=(a,max(b,end),'SECRET' if 'SECRET' in (kind,k) else k)
            else:merged.append((start,end,kind))
        output=[];offset=0;counts={}
        for start,end,kind in merged:
            output.append(text[offset:start]);counts[kind]=counts.get(kind,0)+1
            if kind=='SECRET':replacement='[SECRET_REMOVED]'
            else:
                value=(self.scope+'\0'+kind+'\0'+text[start:end].casefold()).encode()
                digest=hmac.new(self.key,value,hashlib.sha256).hexdigest()[:20]
                replacement='[ARCIA_'+re.sub('[^A-Z_]','_',kind.upper())+'_'+digest+']'
            output.append(replacement);offset=end
        output.append(text[offset:]);result=''.join(output)
        residual=TOKEN.sub('',result)
        if any(p.search(residual) for p in SECRETS) or any(p.search(residual) for _,p in TECHNICAL):raise Blocked('RESIDUAL_SENSITIVE_PATTERN')
        if any(i in residual.casefold() for i in self.identifiers):raise Blocked('RESIDUAL_CLIENT_IDENTIFIER')
        return result,counts

    def payload(self,value):
        if not isinstance(value,dict) or set(value)-{'messages','documents','tool_results','metadata'}:raise Blocked('UNSUPPORTED_PAYLOAD')
        if not isinstance(value.get('messages'),list) or not 1<=len(value['messages'])<=100:raise Blocked('MESSAGES_REQUIRED')
        output={'messages':[]};counts={};size=0
        def clean(text):
            nonlocal size
            if not isinstance(text,str):raise Blocked('TEXT_ONLY_NO_FILES_IMAGES_OR_TOOLS')
            size+=len(text)
            if size>MAX_TEXT:raise Blocked('PAYLOAD_TOO_LARGE')
            sanitized,found=self.text(text)
            for k,n in found.items():counts[k]=counts.get(k,0)+n
            return sanitized
        for message in value['messages']:
            if not isinstance(message,dict) or set(message)!={'role','content'} or message['role'] not in ('system','user','assistant','tool'):raise Blocked('UNSUPPORTED_MESSAGE')
            output['messages'].append({'role':message['role'],'content':clean(message['content'])})
        for key in ('documents','tool_results'):
            if key in value:
                if not isinstance(value[key],list) or len(value[key])>100:raise Blocked('UNSUPPORTED_COLLECTION')
                output[key]=[clean(text) for text in value[key]]
        if 'metadata' in value:
            metadata=value['metadata']
            if not isinstance(metadata,dict) or set(metadata)-{'title','filename'}:raise Blocked('UNSUPPORTED_METADATA')
            output['metadata']={k:clean(v) for k,v in metadata.items()}
        return {'payload':output,'detections':counts,'cloud_authorized':False,
                'policy':'local_preview_only','raw_mapping_stored':False}

    def completion(self,value):
        """Filter every content-bearing field; never let caller choose a provider.

        Protocol names/JSON keys must survive detection unchanged, or the whole
        request is refused. This preserves tool schemas without exporting PII in
        a key or silently renaming a function. Images and encoded files are denied.
        """
        allowed={'model','messages','tools','tool_choice','parallel_tool_calls','stream','stream_options',
                 'temperature','top_p','max_tokens','max_completion_tokens','stop','response_format',
                 'presence_penalty','frequency_penalty','seed','reasoning','verbosity'}
        if not isinstance(value,dict) or set(value)-allowed:raise Blocked('UNSUPPORTED_COMPLETION_FIELD')
        if not isinstance(value.get('messages'),list) or not 1<=len(value['messages'])<=100:raise Blocked('MESSAGES_REQUIRED')
        total=0;counts={}
        def clean(text,protocol=False):
            nonlocal total
            total+=len(text)
            if total>MAX_TEXT:raise Blocked('PAYLOAD_TOO_LARGE')
            result,found=self.text(text)
            if protocol and result!=text:raise Blocked('SENSITIVE_PROTOCOL_IDENTIFIER')
            for key,n in found.items():counts[key]=counts.get(key,0)+n
            return result
        def tree(item,depth=0,protocol=False):
            if depth>20:raise Blocked('NESTING_LIMIT')
            if isinstance(item,str):return clean(item,protocol)
            if item is None or isinstance(item,(bool,int,float)):return item
            if isinstance(item,list):return [tree(x,depth+1,protocol) for x in item]
            if isinstance(item,dict):return {clean(k,True):tree(v,depth+1,k in ('name','type','format','$ref')) for k,v in item.items()}
            raise Blocked('UNSUPPORTED_JSON_VALUE')
        output={k:v for k,v in value.items() if k not in ('messages','tools','tool_choice','response_format','stop')}
        output['messages']=[]
        for msg in value['messages']:
            if not isinstance(msg,dict) or set(msg)-{'role','content','name','tool_calls','tool_call_id'}:raise Blocked('UNSUPPORTED_MESSAGE')
            if msg.get('role') not in ('system','developer','user','assistant','tool'):raise Blocked('UNSUPPORTED_ROLE')
            result={'role':msg['role']}
            content=msg.get('content')
            if isinstance(content,list):
                if any(not isinstance(x,dict) or set(x)!={'type','text'} or x['type']!='text' for x in content):raise Blocked('TEXT_ONLY_NO_IMAGES_FILES')
                result['content']=[{'type':'text','text':clean(x['text'])} for x in content]
            elif content is None and msg['role']=='assistant':result['content']=None
            elif isinstance(content,str):result['content']=clean(content)
            else:raise Blocked('TEXT_CONTENT_REQUIRED')
            for k in ('name','tool_call_id'):
                if k in msg:result[k]=clean(msg[k],True)
            if 'tool_calls' in msg:
                calls=msg['tool_calls']
                if not isinstance(calls,list) or len(calls)>32:raise Blocked('TOOL_CALL_LIMIT')
                result['tool_calls']=[]
                for call in calls:
                    if set(call)!={'id','type','function'} or call['type']!='function' or set(call['function'])!={'name','arguments'}:raise Blocked('UNSUPPORTED_TOOL_CALL')
                    arguments=json.loads(call['function']['arguments'])
                    result['tool_calls'].append({'id':clean(call['id'],True),'type':'function','function':{
                        'name':clean(call['function']['name'],True),'arguments':json.dumps(tree(arguments),ensure_ascii=False)}})
            output['messages'].append(result)
        for k in ('tools','tool_choice','response_format','stop'):
            if k in value:output[k]=tree(value[k])
        # Non-content options are tightly bounded and cannot carry arbitrary text.
        for k in set(output)-{'messages','tools','tool_choice','response_format','stop','model','stream','stream_options'}:
            if k in ('reasoning','verbosity'):
                output[k]=tree(output[k])
            elif not isinstance(output[k],(int,float)) or isinstance(output[k],bool):raise Blocked('NUMERIC_OPTION_REQUIRED')
        if not isinstance(output.get('stream',False),bool):raise Blocked('BOOLEAN_STREAM_REQUIRED')
        if 'stream_options' in output and output['stream_options']!={'include_usage':True}:raise Blocked('UNSUPPORTED_STREAM_OPTIONS')
        return output,counts
