"""YAML 1.2식 불리언: true/false만 불리언으로 본다.

PyYAML 기본(YAML 1.1)은 `no`, `yes`, `on`, `off`도 불리언으로 읽어서
항목 필드 `no:`가 False 키가 되어 버린다.
"""

import re

import yaml


class Loader(yaml.SafeLoader):
    pass


Loader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:bool"]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


def load(text: str):
    return yaml.load(text, Loader=Loader)


def compose(text: str):
    return yaml.compose(text, Loader=Loader)
