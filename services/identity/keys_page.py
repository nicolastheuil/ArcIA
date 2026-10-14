"""Personal provider configuration UI; never fetch or render a stored secret."""
import html
import json


def render_keys_page(csrf, nonce, providers):
    options=''.join('<option value="'+html.escape(name,quote=True)+'">'+html.escape(label)+'</option>'
                    for name,label in providers.items())
    return '''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>ArcIA — mes clés IA</title><style>
body{font:17px system-ui;max-width:760px;margin:6vh auto;padding:24px;color:#15354a;background:#f6f9fb}
main{background:white;border-radius:16px;padding:32px;border:1px solid #dce6ed}h1{font-size:28px}
label{display:block;margin:18px 0 6px}input,select,button{font:inherit;padding:10px;border:1px solid #9eb4c4;border-radius:6px}
input{box-sizing:border-box;width:100%}button{cursor:pointer;background:#155c92;color:white}li{margin:16px 0}
a{color:#155c92}small{display:block;margin:8px 0}button:disabled{opacity:.5}</style>
<main><a href="/portal/">Mon espace ArcIA</a> · <a href="/account">Mon compte</a>
<h1>Mes clés IA</h1><p>Vos clés sont chiffrées et réservées à votre compte. Leur valeur ne sera plus affichée après enregistrement.</p>
<p><strong>L’enregistrement ne les active pas pour vos conversations.</strong> L’activation du routage personnel reste à qualifier par l’administrateur.</p>
<form id="keys"><label for="provider">Fournisseur</label><select id="provider">'''+options+'''</select>
<label for="api-key">Clé API</label><input id="api-key" type="password" autocomplete="off" spellcheck="false" required minlength="8" maxlength="8192">
<small>Utilisez une clé API du fournisseur. Une nouvelle saisie remplace la clé enregistrée pour ce fournisseur.</small>
<button id="save" type="submit">Enregistrer / remplacer</button></form>
<p id="status" role="status" aria-live="polite"></p><h2>Clés enregistrées</h2><ul id="list"></ul></main>
<script nonce="'''+html.escape(nonce,quote=True)+'''">
const csrf='''+json.dumps(csrf)+''', providers='''+json.dumps(providers)+''';
const status=document.getElementById('status'),list=document.getElementById('list'),input=document.getElementById('api-key');
let busy=false;
function show(rows){list.replaceChildren();if(!rows.length){list.textContent='Aucune clé enregistrée.';return;}
for(const row of rows){const li=document.createElement('li');li.textContent=providers[row.provider]+' — enregistrée, inactive. ';
const button=document.createElement('button');button.type='button';button.textContent='Supprimer';
button.onclick=()=>change('DELETE',{provider:row.provider});li.append(button);list.append(li);}}
async function change(method,value){if(busy)return;busy=true;document.getElementById('save').disabled=true;
input.value='';status.textContent='Enregistrement en cours…';try{
const r=await fetch('/portal/api/keys',{method,headers:{'Content-Type':'application/json','X-ArcIA-CSRF':csrf},body:JSON.stringify(value)});
const x=await r.json();if(!r.ok)throw new Error(r.status===403?'Habilitation retirée ou session expirée. Reconnectez-vous.':r.status===409?'Une modification concurrente a eu lieu. Rechargez la page.':'Enregistrement impossible. Réessayez.');
show(x.keys);status.textContent=method==='DELETE'?'Clé supprimée.':'Clé enregistrée et chiffrée. Elle reste inactive.';
}catch(e){status.textContent=e.message;}finally{value.api_key='';busy=false;document.getElementById('save').disabled=false;}}
document.getElementById('keys').onsubmit=e=>{e.preventDefault();change('POST',{provider:document.getElementById('provider').value,api_key:input.value});};
fetch('/portal/api/keys').then(async r=>{if(!r.ok)throw new Error();show((await r.json()).keys);}).catch(()=>status.textContent='Liste indisponible. Reconnectez-vous.');
</script></html>'''
