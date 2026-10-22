// Citizen contract only; Intake keeps its native texte/image/audio/video API.
const item=$input.first(), b=item.json.body, errors=[];
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const body=object(b)?b:{};
const report_id=typeof body.report_id==='string'?body.report_id.trim():'';
const description=typeof body.description==='string'?body.description:'';
if(!/^[A-Za-z0-9_-]{3,64}$/.test(report_id))errors.push('INVALID_REPORT_ID');
if((body.description!==undefined&&typeof body.description!=='string')||description.length>3000)errors.push('INVALID_DESCRIPTION');
if(Object.keys(body).some(k=>!['report_id','description','location'].includes(k)))errors.push('UNSUPPORTED_FORM_FIELD');
let location=null;
if(body.location!==undefined&&body.location!==''){
  try{
    location=typeof body.location==='string'?JSON.parse(body.location):body.location;
    if(location!==null){
      if(!object(location)||Object.keys(location).some(k=>!['address','latitude','longitude'].includes(k)))throw Error();
      for(const [key,limit] of [['latitude',90],['longitude',180]]){
        const v=location[key];if(v!==undefined&&v!==null&&(typeof v!=='number'||!Number.isFinite(v)||Math.abs(v)>limit))throw Error();
      }
      if(location.address!==undefined&&location.address!==null&&(typeof location.address!=='string'||location.address.length>300))throw Error();
    }
  }catch{errors.push('INVALID_LOCATION');location=null;}
}
const files={...(item.binary||{})};
// Preserve the previous single-image alias, but never infer audio/video from it.
const keys=Object.keys(files);
if(keys.length===1&&!['image','audio','video'].includes(keys[0])&&['image/jpeg','image/png','image/webp'].includes(files[keys[0]]?.mimeType)){
  files.image=files[keys[0]];delete files[keys[0]];
}
if(Object.keys(files).some(k=>!['image','audio','video'].includes(k)))errors.push('UNSUPPORTED_OR_DUPLICATE_MEDIA_FIELD');
const image=Boolean(files.image),audio=Boolean(files.audio),video=Boolean(files.video);
if((video&&(image||audio))||(!video&&!image))errors.push('UNSUPPORTED_MEDIA_COMBINATION');
if(image&&!audio&&description.trim().length<5)errors.push('DESCRIPTION_OR_AUDIO_REQUIRED');
const mime={image:['image/jpeg','image/png','image/webp'],
  audio:['audio/wav','audio/x-wav','audio/wave','audio/mpeg','audio/mp3','audio/mp4','audio/x-m4a','audio/ogg','audio/webm','audio/flac','audio/x-flac'],
  video:['video/mp4','video/webm','video/quicktime','video/x-msvideo','video/x-matroska']};
for(const kind of ['image','audio','video'])if(files[kind]&&!mime[kind].includes(files[kind].mimeType))errors.push('UNSUPPORTED_'+kind.toUpperCase()+'_TYPE');
const mode=video?'video':audio?'image_audio':'image_text';
const decision=errors.length?'REJECT':'PASS';
const x={report_id:report_id||null,original:{description,location},submission:{mode,has_audio:audio,has_video:video},decision,
  errors:[...new Set(errors)],review_reasons:[],policy:{gate_1:{decision:'NOT_RUN',reason_codes:[]}},
  integration:__INTEGRATION_CONFIG__,
  components:{intake:{execution:'not_called',inference:'not_verified'},vision:{execution:'not_called'},knowledge:{execution:'not_called'},persistence:{execution:'not_called'}},
  trace:[{at:new Date().toISOString(),stage:'INPUT_CHECK',decision,reason_codes:[...new Set(errors)]}]};
return [{json:x,...(!errors.length?{binary:files}:{})}];
