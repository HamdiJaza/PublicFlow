"""Unchanged native API in an isolated copy, with correlation headers only."""
from contextvars import ContextVar
import json
from pathlib import Path
import sys
import time
import uuid

from common import RUNTIME,configure,prepare
from evidence import RECEIPTS,sha

prepare();configure();sys.path.insert(0,str(RUNTIME))
from api import knowledge_agent as native

active_receipt=ContextVar('knowledge_receipt',default=None)
original_save=native.save_record


def save_record(record):
    original_save(record)
    receipt_id=active_receipt.get()
    if receipt_id and record.get('status')=='completed':
        RECEIPTS.mkdir(parents=True,exist_ok=True)
        payload={'created_at_epoch':time.time(),'native_record':record}
        with (RECEIPTS/(receipt_id+'.json')).open('x',encoding='utf-8') as output:
            json.dump(payload,output,ensure_ascii=False,allow_nan=False)


native.save_record=save_record


async def app(scope,receive,send):
    if scope.get('type')!='http' or scope.get('method')!='POST' or scope.get('path')!='/knowledge':
        return await native.app(scope,receive,send)
    receipt_id=uuid.uuid4().hex;marker=active_receipt.set(receipt_id)
    async def correlated(message):
        if message['type']=='http.response.start' and message['status']==200:
            path=RECEIPTS/(receipt_id+'.json')
            if path.is_file():
                record=json.loads(path.read_text(encoding='utf-8'))
                message={**message,'headers':list(message.get('headers',[]))+[
                    (b'x-knowledge-receipt',receipt_id.encode()),(b'x-knowledge-receipt-sha256',sha(record).encode())]}
        await send(message)
    try:await native.app(scope,receive,correlated)
    finally:active_receipt.reset(marker)
