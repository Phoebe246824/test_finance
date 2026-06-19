from graphiti_core.nodes import EpisodeType, EpisodicNode
from graphiti_core.prompts.extract_nodes import ExtractedEntity
from graphiti_core.utils.datetime_utils import utc_now
from graphiti_core.utils.maintenance.node_operations import (
    _create_entity_nodes,
    _drop_generic_alias_nodes_for_explicit_ids,
)


def test_bracketed_customer_id_keeps_full_name_with_latin_suffix():
    episode = EpisodicNode(
        name="finance_case",
        group_id="sentinel",
        labels=["Episodic"],
        source=EpisodeType.text,
        source_description="test",
        content="【P111# 客户K】于2026年6月17日投诉。",
        valid_at=utc_now(),
    )
    extracted_entities = [
        ExtractedEntity(name="客户", entity_type_id=0, episode_indices=[0]),
    ]

    nodes, _ = _create_entity_nodes(
        extracted_entities,
        [{"entity_type_name": "Person"}],
        None,
        [episode],
    )

    person_nodes = [node for node in nodes if node.attributes.get("id_number") == "P111"]
    assert len(person_nodes) == 1
    assert person_nodes[0].name == "客户K"
    assert person_nodes[0].attributes["id_number"] == "P111"


def test_short_generic_customer_alias_is_dropped_for_explicit_id_name():
    episode = EpisodicNode(
        name="finance_case",
        group_id="sentinel",
        labels=["Episodic"],
        source=EpisodeType.text,
        source_description="test",
        content="【P105# 客户E】尝试向【P305# 涉诈账户】转账。",
        valid_at=utc_now(),
    )
    nodes, node_episode_index_map = _create_entity_nodes(
        [ExtractedEntity(name="客户", entity_type_id=0, episode_indices=[0])],
        [{"entity_type_name": "Person"}],
        None,
        [episode],
    )

    nodes = _drop_generic_alias_nodes_for_explicit_ids(nodes, node_episode_index_map)

    assert ("客户E", "P105") in [
        (node.name, node.attributes.get("id_number")) for node in nodes
    ]
    assert ("客户", None) not in [
        (node.name, node.attributes.get("id_number")) for node in nodes
    ]
