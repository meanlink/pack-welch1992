from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset
from src.services.business import metadata, STATION_KEY
from src.utils.serialization import checksum
import math, time
def create(db, data):
    name=data.name.strip()
    if len(name)<2: raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(Dataset).where(Dataset.name==name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')
    for index,row in enumerate(data.records):
        if not isinstance(row,dict): raise HTTPException(422, f'第 {index+1} 行必须为记录对象')
        for c in metadata()['columns']:
            value=row.get(c['key'])
            if value is None or value=='':
                # 工位为可选字段：兼容缺少工位的旧批次
                if c.get('optional'): continue
                raise HTTPException(422, f'第 {index+1} 行缺少字段 {c["label"]}')
            if c['type']=='number':
                try:
                    if isinstance(value,bool) or not math.isfinite(float(value)): raise ValueError()
                    row[c['key']]=float(value)
                except (TypeError, ValueError, OverflowError): raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 必须为有限数值')
            else:
                row[c['key']]=str(value).strip()
    d=Dataset(name=name, source=data.source, records=data.records, checksum=checksum(data.records), created_at=time.time())
    db.add(d); db.flush()
    return d
