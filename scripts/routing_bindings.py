"""Change only owned Hermes model bindings; preserve identity, state and scale."""
import copy
import hashlib
import yaml

BASE='http://omniroute.arcia-routing.svc.cluster.local:20131/v1'


def configure_settings(settings):
    settings['model']={'default':'auto/smart','provider':'custom','base_url':BASE}
    settings['auxiliary']={name:{'provider':'main','model':'auto/smart','base_url':BASE} for name in ('compression','vision')}
    settings.setdefault('platform',{}).update(model_routing='omniroute_admin_policy',cloud_calls_enabled=True,cloud_classification='synthetic')
    settings['platform'].pop('paid_llm_enabled',None)  # Price policy belongs to the instance.


def render(records):
    documents=[]
    for namespace,record in records.items():
        deployment=copy.deepcopy(record['deployment']);config=copy.deepcopy(record['config'])
        settings=yaml.safe_load(config['data']['config.yaml'])
        configure_settings(settings)
        config['data']['config.yaml']=yaml.safe_dump(settings,sort_keys=False)
        digest=hashlib.sha256(config['data']['config.yaml'].encode()).hexdigest()
        name='hermes-config-'+digest[:16]
        config={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name,'namespace':namespace},
            'immutable':True,'data':config['data']}
        spec=deployment['spec']['template']['spec']
        container=next(c for c in spec['containers'] if c['name']=='hermes') if any(c['name']=='hermes' for c in spec['containers']) else spec['containers'][0]
        for env in container.get('env',[]):
            if env['name']=='OPENAI_BASE_URL':env['value']=BASE;env.pop('valueFrom',None)
        next(v for v in spec['volumes'] if v['name']=='config')['configMap']['name']=name
        deployment['spec']['template']['metadata'].setdefault('annotations',{}).update({
            'arcia.io/config-sha256':digest,'arcia.io/model-routing':'omniroute_admin_policy'})
        deployment={'apiVersion':'apps/v1','kind':'Deployment','metadata':{k:copy.deepcopy(deployment['metadata'][k]) for k in ('name','namespace','resourceVersion','uid','labels','annotations') if k in deployment['metadata']},
            'spec':deployment['spec']}
        documents.extend([config,deployment])
    return documents
