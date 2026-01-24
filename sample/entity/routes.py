from django.apps import apps

from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
from bazis.core.schemas import SchemaFields


class ChildEntityRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.ChildEntity')

    fields = {
        None: SchemaFields(
            include={
                'parent_entities': None,
            },
        ),
    }


class DependentEntityRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.DependentEntity')


class ExtendedEntityRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.ExtendedEntity')


class ParentEntityRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.ParentEntity')

    # add fields (extended_entity, dependent_entities) to schema
    fields = {
        None: SchemaFields(
            include={'extended_entity': None, 'dependent_entities': None},
        ),
    }
