"""Real PKCE browser probes and native synthetic-key qualification, no inference."""
import base64
import hashlib
import http.client
from http.cookies import SimpleCookie
from html.parser import HTMLParser
import json
import secrets
import socket
import ssl
import subprocess
import time
import urllib.request
from urllib.parse import urljoin,urlsplit,urlencode
import uuid


class Form(HTMLParser):
    def __init__(self):super().__init__();self.action=None;self.inputs={};self.active=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="form" and attrs.get("id")=="kc-form-login":self.active=True;self.action=attrs.get("action")
        if tag=="input" and self.active and attrs.get("name") and attrs.get("type")=="hidden":self.inputs[attrs["name"]]=attrs.get("value","")
    def handle_endtag(self,tag):
        if tag=="form":self.active=False


class Browser:
    def __init__(self,host,address,certificate):
        self.host=host;self.address=address;self.cookies=SimpleCookie()
        self.context=ssl.create_default_context(cadata=certificate)
    def request(self,method,url,value=None,form=False,csrf=None):
        url=urljoin("https://"+self.host+":20129/personal/",url);parts=urlsplit(url)
        if parts.scheme!="https" or parts.hostname!=self.host or parts.port not in (None,443,20129):raise ValueError("PRIVATE_REDIRECT_REQUIRED")
        port=parts.port or 443
        connection=http.client.HTTPSConnection(self.host,port,context=self.context,timeout=25)
        connection._create_connection=lambda dest,timeout,source_address=None:socket.create_connection((self.address,port),timeout)
        headers={"Origin":"https://"+parts.netloc,"Cookie":"; ".join(k+"="+v.coded_value for k,v in self.cookies.items() if parts.path.startswith(v["path"] or "/"))}
        if csrf:headers["X-ArcIA-CSRF"]=csrf
        body=None
        if value is not None:
            body=urlencode(value).encode() if form else json.dumps(value).encode()
            headers["Content-Type"]="application/x-www-form-urlencoded" if form else "application/json"
        try:
            connection.request(method,parts.path+("?" + parts.query if parts.query else ""),body=body,headers=headers)
            response=connection.getresponse();raw=response.read(1048577)
            if len(raw)>1048576:raise ValueError("RESPONSE_LIMIT")
            for name,value in response.getheaders():
                if name.lower()=="set-cookie":self.cookies.load(value)
            return response.status,raw,response.getheader("Location")
        finally:connection.close()
    def follow(self,url):
        for _ in range(12):
            status,raw,location=self.request("GET",url)
            if status not in (301,302,303,307,308):return status,raw
            url=urljoin(urljoin("https://"+self.host+":20129/personal/",url),location)
        raise ValueError("REDIRECT_LIMIT")
    def login(self,user):
        status,raw=self.follow("/personal/login");form=Form();form.feed(raw.decode())
        if status!=200 or not form.action:raise ValueError("LOGIN_FORM_REQUIRED")
        status,raw,location=self.request("POST",form.action,{**form.inputs,"username":user["username"],"password":user["password"],"credentialId":""},form=True)
        if status not in (302,303) or not location:raise ValueError("LOGIN_REFUSED")
        status,raw=self.follow(location)
        if status!=200 or b"Mes cl" not in raw:raise ValueError("PERSONAL_PAGE_REQUIRED")
        status,raw,_=self.request("GET","/personal/api/state")
        if status!=200:raise ValueError("SESSION_REQUIRED")
        return json.loads(raw)


POD_PROBE=r"""
import json,os,sys,tempfile
from pathlib import Path
sys.path.insert(0,"/personal-code")
from self_service import Identity,Control,owner_id
from native import Native
from store import Store
from gateway import RuntimeIdentity
value=json.load(sys.stdin)
config=json.loads(Path("/personal-code/config.json").read_text())
key=os.environ["STORAGE_ENCRYPTION_KEY"].encode()
real=Store("/data/arcia-self-service/state.db",key)
payload=real.session(value["session"])
identity=Identity(config,key)
checker=RuntimeIdentity(config,json.loads(Path("/routing-identity/checker.json").read_text()),json.loads(Path("/routing-clients/clients.json").read_text()))
identity.role_lookup=checker.live_roles
claims=identity.authenticate(payload["access_token"])
if value.get("role_only"):
    print(json.dumps({"personal_role_present":"ArcIA.ProviderSelfService" in claims["arcia_roles"]}));real.db.close();sys.exit(0)
if "ArcIA.ProviderSelfService" not in claims["arcia_roles"]:raise ValueError("QUALIFICATION_ROLE_REQUIRED")
native=Native(os.environ["JWT_SECRET"])
created=[];technical=[];result={}
with tempfile.TemporaryDirectory(prefix="arcia-routing-qualification-") as directory:
    store=Store(Path(directory)/"state.db",key)
    control=Control(store,native)
    settings=store.settings();settings.update(personal_providers_enabled=True,allowed_models=["openrouter/synthetic-qualification-model"])
    store.save_settings(settings)
    try:
        state=control.create(claims,{"provider":"openrouter","label":"Synthetic qualification","api_key":"synthetic-not-valid-provider-key-"+os.urandom(16).hex()})
        row=store.connections()[0];created.append(row["native_id"])
        other={**claims,"sub":"synthetic-foreign-owner"}
        try:control.delete(other,row["id"]);result["cross_owner_denied"]=False
        except PermissionError:result["cross_owner_denied"]=True
        control.preference(claims,{"enabled":True})
        profile=control.profile(claims);credential=store.credential(owner_id(claims));technical.append(credential["id"])
        metadata=native.request("GET","/api/keys/"+credential["id"])
        result.update(native_personal_connection_created=True,owner_scoped_key_created=profile["connections"]==created,
            no_management_scope=not(set(metadata.get("scopes",[]))&{"manage","admin"}),
            connection_scope_verified=metadata.get("allowedConnections")==created,
            endpoint_scope_verified=metadata.get("allowedEndpoints")==["chat"],
            api_key_not_returned_to_browser="api_key" not in state)
    finally:
        for identifier in technical:native.revoke_key(identifier)
        for identifier in created:native.delete(identifier)
        # Recover an uncertain provider write by its unique qualification name.
        for row in store.connections():
            for connection in native.connections():
                if connection["name"]==row["native_name"]:native.delete(connection["id"])
        store.db.close();real.db.close()
result.update(native_fixtures_removed=True,model_calls_executed=False)
print(json.dumps(result))
"""


def verify(values):
    scope={"__name__":"routing_qualification_support"};exec(values["identity_worker_source"],scope)
    operation=values["operation_id"]
    scope["owned"]("Namespace","arcia-routing",None,operation)
    tls=scope["owned"]("Secret","routing-tls","arcia-routing-lan",operation)
    certificate=base64.b64decode(tls["data"]["tls.crt"]).decode()
    fixtures=[];browsers=[];checks={}
    with scope["forward"]() as base:
        admin=scope["Admin"](base,values["hostname"]);admin.authenticate(values["credentials"])
        if admin.resource().get("attributes",{}).get("arcia.operation-id")!=operation:raise ValueError("FOREIGN_REALM")
        try:
            roles={name:admin.resource("/roles/"+name) for name in ("ArcIA.User","ArcIA.ProviderSelfService","ArcIA.Admin")}
            for label,extra in (("personal","ArcIA.ProviderSelfService"),("standard",None),("admin","ArcIA.Admin")):
                user={"username":"arcia-routing-qualification-"+secrets.token_hex(8)+"@example.invalid","password":secrets.token_urlsafe(36)}
                fixtures.append(user)  # Reserve before the external write.
                body={"username":user["username"],"enabled":True,"email":user["username"],
                    "firstName":"Synthetic","lastName":"Qualification","requiredActions":[],"emailVerified":True,
                    "attributes":{"arcia.qualification-owner":[operation]},
                    "credentials":[{"type":"password","value":user["password"],"temporary":False}]}
                request=urllib.request.Request(admin.base+"/admin/realms/arcia/users",method="POST",data=json.dumps(body).encode(),
                    headers={"Host":admin.host,"X-Forwarded-Proto":"https","Authorization":"Bearer "+admin.token,"Content-Type":"application/json"})
                with urllib.request.urlopen(request,timeout=25) as response:
                    user["id"]=str(uuid.UUID(response.headers["Location"].rstrip("/").rsplit("/",1)[1]))
                current=admin.resource("/users/"+user["id"])
                if current.get("attributes",{}).get("arcia.qualification-owner")!=[operation]:raise ValueError("FIXTURE_SCOPE_REQUIRED")
                admin.resource("/users/"+user["id"]+"/role-mappings/realm","POST",[roles["ArcIA.User"]]+([roles[extra]] if extra else []))
                browser=Browser(values["hostname"],values["vip"],certificate);browsers.append(browser)
                state=browser.login(user)
                checks[label+"_pkce_login"]=True
                checks[label+"_admin_boundary"]=state["admin"]==(label=="admin")
                status,_,_=browser.request("POST","/personal/api/connections",{"provider":"openrouter","label":"Denied fixture","api_key":"synthetic-unused-key"},csrf="wrong-csrf")
                checks[label+"_csrf_denied"]=status==403
                if label=="standard":
                    status,_,_=browser.request("POST","/personal/api/connections",{"provider":"openrouter","label":"Denied fixture","api_key":"synthetic-unused-key"},csrf=state["csrf"])
                    checks["standard_personal_write_denied"]=status==403
                status,_,_=browser.request("GET","/api/providers")
                checks[label+"_native_management_denied"]=status in (401,403)
            personal=browsers[0]
            session=personal.cookies["__Secure-arcia_routing_session"].value
            result=subprocess.run(["/usr/local/bin/k3s","kubectl","exec","-i","deployment/omniroute","-n","arcia-routing","-c","personal","--",
                "/opt/hermes/.venv/bin/python","-c",POD_PROBE],input=json.dumps({"session":session}).encode(),capture_output=True,timeout=180)
            if result.returncode:raise RuntimeError("NATIVE_SELF_SERVICE_QUALIFICATION_FAILED\n"+result.stderr.decode(errors="replace"))
            probe=json.loads(result.stdout)
            checks.update({k:v for k,v in probe.items() if k!="model_calls_executed"})
            admin.resource("/users/"+fixtures[0]["id"]+"/role-mappings/realm","DELETE",[roles["ArcIA.ProviderSelfService"]])
            status,raw,_=personal.request("GET","/personal/api/state")
            checks["role_withdrawal_live_denied"]=status==200 and json.loads(raw)["personal_allowed"] is False
            withdrawal=subprocess.run(["/usr/local/bin/k3s","kubectl","exec","-i","deployment/omniroute","-n","arcia-routing","-c","personal","--",
                "/opt/hermes/.venv/bin/python","-c",POD_PROBE],input=json.dumps({"session":session,"role_only":True}).encode(),capture_output=True,timeout=60)
            checks["online_role_authority_withdrawal_verified"]=withdrawal.returncode==0 and json.loads(withdrawal.stdout)["personal_role_present"] is False
            admin.resource("/users/"+fixtures[0]["id"],"PUT",{"enabled":False})
            status,_,_=personal.request("GET","/personal/api/state")
            checks["disabled_user_live_denied"]=status in (401,403)
        finally:
            for user in fixtures:
                if "id" not in user:
                    # Reconcile an uncertain create by its reserved unique name.
                    for _ in range(5):
                        matches=admin.resource("/users?username="+user["username"]+"&exact=true")
                        if matches:break
                        time.sleep(0.2)
                    if not matches:continue
                    if len(matches)!=1:raise ValueError("FIXTURE_CLEANUP_SCOPE_REQUIRED")
                    user["id"]=matches[0]["id"]
                current=admin.resource("/users/"+user["id"])
                if (current.get("attributes",{}).get("arcia.qualification-owner")!=[operation]
                        or current.get("username")!=user["username"] or current.get("lastName")!="Qualification"):
                    raise ValueError("FIXTURE_CLEANUP_SCOPE_REQUIRED")
                admin.resource("/users/"+user["id"],"DELETE")
    return {"passed":bool(checks) and all(checks.values()),"checks":checks,"fixtures_removed":len(fixtures),
        "model_calls_executed":False,"tls_validation_bypassed":False}


if __name__=="__main__":print(json.dumps(verify(ARCIA_INPUT)))
