const item = $input.first();
const body = item.json.body;
const errors = [];
const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const b = object(body) ? body : {};
const report_id = typeof b.report_id === 'string' ? b.report_id.trim() : '';
const description = typeof b.description === 'string' ? b.description : '';
if (!/^[A-Za-z0-9_-]{3,64}$/.test(report_id)) errors.push('INVALID_REPORT_ID');
if (description.trim().length < 5 || description.length > 3000) errors.push('INVALID_DESCRIPTION');
if (Object.keys(b).some(k => !['report_id','description','location'].includes(k))) errors.push('UNSUPPORTED_FORM_FIELD');
let location = null;
if (b.location !== undefined && b.location !== '') {
  try {
    location = typeof b.location === 'string' ? JSON.parse(b.location) : b.location;
    if (location !== null) {
      if (!object(location) || Object.keys(location).some(k=>!['address','latitude','longitude'].includes(k))) throw Error();
      for (const [name,limit] of [['latitude',90],['longitude',180]]) {
        const v=location[name];
        if (v !== undefined && v !== null && (typeof v !== 'number' || !Number.isFinite(v) || Math.abs(v)>limit)) throw Error();
      }
      if (location.address !== undefined && location.address !== null && (typeof location.address !== 'string' || location.address.length>300)) throw Error();
    }
  } catch { errors.push('INVALID_LOCATION'); location=null; }
}
const files=item.binary || {};
const keys=Object.keys(files);
if (keys.length!==1) errors.push(keys.length===0?'MISSING_IMAGE':'EXACTLY_ONE_IMAGE_REQUIRED');
if (keys.length===1 && files[keys[0]].mimeType && !['image/jpeg','image/png','image/webp'].includes(files[keys[0]].mimeType)) errors.push('UNSUPPORTED_MEDIA_TYPE');
const decision=errors.length?'REJECT':'PASS';
const result={json:{report_id:report_id||null,original:{description,location},decision,
  errors,review_reasons:[],policy:{gate_1:{decision:'NOT_RUN',reason_codes:[]}},
  integration:__INTEGRATION_CONFIG__,
  components:{intake:{execution:'not_called',inference:'not_verified'},vision:{execution:'not_called'},knowledge:{execution:'not_called'},persistence:{execution:'not_called'}},
  trace:[{at:new Date().toISOString(),stage:'INPUT_CHECK',decision,reason_codes:errors}]}};
if (!errors.length) result.binary={image:files[keys[0]]};
return [result];
