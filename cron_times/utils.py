import collections.abc
import logging
from pathlib import Path
from typing import Iterable

import colorlog
import ruamel.yaml
import ruamel.yaml.scalarstring

logger = logging.getLogger(__name__)
yaml = ruamel.yaml.YAML()

yaml.sort_base_mapping_type_on_output = False


def setup_logging():
    colorlog.basicConfig(
        level=logging.INFO,
        format="%(log_color)s[%(levelname)s]%(reset)s %(message)s",
    )


def dump(file_: Path, overwrite: bool, tasks: Iterable[dict]):
    """Write tasks to the file."""
    if file_.exists() and not overwrite:
        logger.error("Target file %s exists. Data not saved.", file_)
        return

    tasks = set_style(tasks)
    with file_.open("w") as fd:
        yaml.dump(tasks, fd)

    logger.info("%d tasks written into %s", len(tasks), file_)


def set_style(item):
    if isinstance(item, dict):
        return {k: set_style(v) for k, v in item.items()}

    elif isinstance(item, str):
        if item.find("\n") > 0:
            # use literal string (|) style for multiline string
            return ruamel.yaml.scalarstring.LiteralScalarString(item)

    elif isinstance(item, collections.abc.Iterable):
        # transform iterable objects to list
        return [set_style(elem) for elem in item]

    return item
