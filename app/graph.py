from rdflib import BNode, Graph, Literal, Namespace, RDF, URIRef

from .models import Scenario


def export_turtle(identifier: str, scenario: Scenario) -> str:
    graph = Graph()
    vocab = Namespace('urn:disaster:vocab:')
    base = f'urn:disaster:scenario:{identifier}:'
    graph.bind('dc', vocab)
    root = URIRef(base)
    graph.add((root, RDF.type, vocab.Scenario))
    for field in ('title', 'exercise', 'horizon_minutes', 'max_risk'):
        graph.add((root, vocab[field], Literal(getattr(scenario, field))))
    for kind, entities in [('team', scenario.teams), ('site', scenario.sites), ('evidence', scenario.evidence)]:
        for entity in entities:
            subject = URIRef(f'{base}{kind}:{entity.id}')
            graph.add((root, vocab[kind], subject))
            graph.add((subject, RDF.type, vocab[kind.capitalize()]))
            for key, value in entity.model_dump().items():
                if key == 'equipment':
                    continue
                for item in value if isinstance(value, (set, list)) else [value]:
                    obj = URIRef(f'{base}evidence:{item}') if key == 'evidence_ids' else Literal(item)
                    graph.add((subject, vocab[key], obj))
    for owner, quantities in [(root, scenario.equipment),
                              *((URIRef(f'{base}site:{s.id}'), s.equipment) for s in scenario.sites)]:
        for name, count in quantities.items():
            node = BNode()
            graph.add((owner, vocab.equipment, node))
            graph.add((node, vocab.name, Literal(name)))
            graph.add((node, vocab.quantity, Literal(count)))
    return graph.serialize(format='turtle')
