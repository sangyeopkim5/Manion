# libs/io_utils.py
import json, yaml, hashlib
from typing import Any, Dict
from jsonschema import validate, Draft202012Validator

def yaml_to_json_dict(yaml_text: str) -> Dict[str, Any]:
    return yaml.safe_load(yaml_text)

def validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> None:
    Draft202012Validator(schema).validate(data)

def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# 매우 작은 JSON 스키마(필수 필드만) — 심화 스키마는 필요 시 확장
CALC_MIN_SCHEMA = {
  "type": "object",
  "required": ["scene","calcs"],
  "properties": {
    "scene": {"type":"object","required":["id"],"properties":{"id":{"type":"string"}}},
    "calcs": {"type":"array","minItems":1}
  }
}
