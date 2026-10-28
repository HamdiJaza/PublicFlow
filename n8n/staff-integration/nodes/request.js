// Staff console contract only; scope and transitions are enforced by municipal.staff_api.
const b=$input.first().json.body, object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const body=object(b)?b:{}, actor=object(body.actor)?body.actor:{};
const allowed=['action','actor','tracking_id','expected_version','status','note','public_note','organisation',
  'category','severity','code','name_fr','name_ar','active'];
const request={};
for(const k of allowed)if(k in body&&k!=='actor')request[k]=body[k];
request.actor={name:actor.name,role:actor.role,organisation:actor.organisation??null};
const valid=typeof request.action==='string'&&/^[a-z_]{2,20}$/.test(request.action)&&
  Object.keys(body).every(k=>allowed.includes(k))&&['MUNICIPALITY','UTILITY','ADMIN'].includes(request.actor.role);
return [{json:{valid,request}}];
