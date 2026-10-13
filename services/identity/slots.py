"""Bounded personal runtime allocation; never reassign a retained identity."""
import base64
import json
import threading


class CapacityError(Exception):pass
class BindingError(Exception):pass


class Slots:
    def __init__(self, api, slots, issuer, operation):
        self.api=api;self.slots=slots;self.issuer=issuer;self.operation=operation
        self.lock=threading.Lock()

    def resource(self,slot,kind,name,group='/api/v1'):
        return group+'/namespaces/'+slot['namespace']+'/'+kind+'/'+name

    def binding(self,slot):
        path=self.resource(slot,'configmaps','slot-binding')
        doc=self.api('GET',path)
        if doc['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=self.operation:
            raise BindingError('FOREIGN_SLOT')
        value=json.loads(doc['data']['binding.json'])
        return path,doc,value

    def allocate(self,subject):
        if not isinstance(subject,str) or not 1<=len(subject)<=128:raise BindingError('INVALID_SUBJECT')
        with self.lock:
            empty=[]
            for slot in self.slots:
                path,doc,value=self.binding(slot)
                if value.get('issuer')==self.issuer and value.get('subject')==subject:return slot
                if not value:empty.append((slot,path,doc))
            if not empty:raise CapacityError('PERSONAL_RUNTIME_CAPACITY_REACHED')
            slot,path,doc=empty[0]
            doc['data']['binding.json']=json.dumps({'issuer':self.issuer,'subject':subject},sort_keys=True)
            # resourceVersion makes a concurrent or stale controller fail closed.
            self.api('PUT',path,doc)
            return slot

    def progress(self,subject):
        slot=self.allocate(subject)
        path=self.resource(slot,'secrets','arcia-oidc-runtime')
        secret=self.api('GET',path)
        current=base64.b64decode(secret['data'].get('ARCIA_IDENTITY_OWNER_SUBJECT','')).decode()
        if current and current!=subject:raise BindingError('SUBJECT_REBIND_REFUSED')
        if not current:
            self.api('PATCH',path,{'metadata':{'resourceVersion':secret['metadata']['resourceVersion']},
                'data':{'ARCIA_IDENTITY_OWNER_SUBJECT':base64.b64encode(subject.encode()).decode()}})
        job_path=self.resource(slot,'jobs',slot['job'],'/apis/batch/v1')
        job=self.api('GET',job_path)
        if job.get('spec',{}).get('suspend'):
            self.api('PATCH',job_path,{'metadata':{'resourceVersion':job['metadata']['resourceVersion']},'spec':{'suspend':False}})
            return {'phase':'installing'}
        if job.get('status',{}).get('failed'):return {'phase':'blocked'}
        if not job.get('status',{}).get('succeeded'):return {'phase':'installing'}
        for name in ('context7-docs','hermes-pilot'):
            path=self.resource(slot,'deployments',name,'/apis/apps/v1')+'/scale'
            scale=self.api('GET',path)
            if scale.get('spec',{}).get('replicas',0)!=1:
                # Kubernetes may omit zero replicas in a Scale representation.
                patch={'spec':{'replicas':1}}
                if scale.get('metadata',{}).get('resourceVersion'):
                    patch['metadata']={'resourceVersion':scale['metadata']['resourceVersion']}
                self.api('PATCH',path,patch)
        return {'phase':'starting','prefix':slot['prefix'],'namespace':slot['namespace']}
