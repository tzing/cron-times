import collections.abc
import logging
import typing
from pathlib import Path
from typing import Iterable

import colorlog
import ruamel.yaml
import ruamel.yaml.scalarstring

if typing.TYPE_CHECKING:
    from ruamel.yaml.compat import MutableSliceableSequence

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


def update_task_definition(
    file_: Path,
    primary_key: str,
    new_data_list: Iterable[dict],
    update_fields: list[str],
    keep_untracked: bool,
):
    """Update task definition to the file."""
    new_data_list = set_style(new_data_list)
    new_data_map = {d[primary_key]: d for d in new_data_list}

    logger.info("Update %d records to %s", len(new_data_list), file_)

    # read
    if file_.exists():
        with file_.open("r") as fd:
            doc: MutableSliceableSequence = yaml.load(fd) or []
    else:
        doc = []

    # check/update existing data
    output_keys = set()
    need_remove = []

    for data in doc:
        data: dict
        key = data[primary_key]

        if key in new_data_map:
            # existing task present in new list
            if update_dict_partial(data, new_data_map[key], update_fields):
                logger.info("Update task#%s (%s)", key, data.get("name"))
            output_keys.add(key)

        else:
            # existing task not found on new list
            if keep_untracked:
                output_keys.add(key)
            else:
                need_remove.append(data)  # remove later

    for data in need_remove:
        logger.info("Remove task#%s (%s)", data.get(primary_key), data.get("name"))
        doc.remove(data)

    # insert
    for data in new_data_list:
        data: dict
        key = data[primary_key]

        if key not in output_keys:
            logger.info("Insert task#%s (%s)", key, data.get("name"))
            doc.append(data)

    # write
    with file_.open("w") as fd:
        yaml.dump(doc, fd)


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


def update_dict_partial(a: dict, b: dict, fields: list[str]) -> bool:
    """Like `dict.update()` but only do partial."""
    changed = False

    for field in fields:
        value_a = a.get(field)
        value_b = b.get(field)

        if not value_b:
            del a[field]
            changed = True
        elif value_a != value_b:
            a[field] = value_b
            changed = True

    return changed
