const x=$input.first().json;
const copy=v=>JSON.parse(JSON.stringify(v));
const media=x.current_media||x.intake_native.media[0];
x.vision_frames=x.vision_frames||[];
x.vision_frames.push({media_id:media.id,sha256:media.sha256,http:copy(x.vision_http),
  native:copy(x.vision_native),gate_2:copy(x.policy.gate_2),transfer:copy(x.media_transfer)});
const expected=x.submission?.mode==='video'?3:1;
const assessed=x.vision_frames.filter(f=>f.http.status_code===200&&f.native!==null).length;
x.visual_assessment={expected_frames:expected,attempted_frames:x.vision_frames.length,assessed_frames:assessed,
  coverage:assessed===expected?'COMPLETE':'INCOMPLETE'};
x.policy.gate_2.checks={...x.policy.gate_2.checks,...x.visual_assessment};
x.components.vision.requests_attempted=x.vision_frames.length;
x.components.vision.native_responses_received=assessed;
return [{json:x}];
