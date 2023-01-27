import logging
from pathlib import Path
from typing import Iterable

import ruamel.yaml
import ruamel.yaml.scalarstring

logger = logging.getLogger(__name__)
yaml = ruamel.yaml.YAML()

yaml.sort_base_mapping_type_on_output = False


def dump(file_: Path, overwrite: bool, tasks: Iterable[dict]):
    """Write tasks to the file."""
    if file_.exists() and not overwrite:
        logger.error("Target file %s exists. Data not saved.", file_)
        return

    tasks = formatting(tasks)
    with file_.open("w") as fd:
        yaml.dump(tasks, fd)

    logger.info("%d tasks written into %s", len(tasks), file_)


def formatting(tasks: Iterable[dict]) -> list[str]:
    output = []
    for item in tasks:
        output.append({k: add_style(v) for k, v in item.items()})
    return output


def add_style(s):
    if not isinstance(s, str):
        return s
    if s.find("\n") > 0:
        return ruamel.yaml.scalarstring.LiteralScalarString(s)
    return s
