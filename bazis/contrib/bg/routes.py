from django.apps import apps

from bazis.contrib.author.routes_abstract import AuthorRouteMixin


class BgRoute(AuthorRouteMixin):
    model = apps.get_model('bg.Task')
    actions = ['action_list', 'action_retrieve']
