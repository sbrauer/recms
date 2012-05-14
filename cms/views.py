from pyramid.renderers import get_renderer, render, render_to_response
from pyramid.httpexceptions import HTTPFound, HTTPForbidden, HTTPNotFound
from resources import Object, Folder, Root, User, Group, Content, widgets
from resources.permissions import *
from resources.users import generate_random_password
from cms.filetempstore import MongoFileUploadTempStore
import colander, deform
import dbutil
from deform.widget import filedict
from pyramid.response import Response
from bson.objectid import ObjectId
from pyramid import security
from pyramid.traversal import find_root
import random
import command
from resources.history import HistoryCollection
from pyramid.view import render_view_to_response
from cms import formatters
from cms.exceptions import *

# Setup a directory to override some of the deform templates.
from pkg_resources import resource_filename
deform_templates = resource_filename('deform', 'templates')
recms_deform_templates = resource_filename('cms', 'templates/deform')
search_path = (recms_deform_templates, deform_templates)
deform.Form.set_zpt_renderer(search_path)

PASTE_BUFFER = "paste_buffer"
NAME_INPUT_SIZE = 50

def get_actions(context, request):
    actions = {'context':[], 'add':[], 'global':[]}
    root = request.root
    if security.authenticated_userid(request):
        if isinstance(context, Group):
            if has_permission(VIEW, context, request):
                actions['context'].append(dict(title='View', url=request.resource_url(context)))
            if not context.is_system_group():
                if has_permission(EDIT, context, request):
                    actions['context'].append(dict(title='Delete', url=request.resource_url(context, 'delete')))
        elif isinstance(context, Object):
            if has_permission(VIEW, context, request):
                actions['context'].append(dict(title='View', url=request.resource_url(context)))
            if has_permission(EDIT, context, request):
                actions['context'].append(dict(title='Edit', url=request.resource_url(context, 'edit')))
            if isinstance(context, User):
                if has_permission(EDIT, context, request):
                    actions['context'].append(dict(title='Set password', url=request.resource_url(context, 'password')))
            if not isinstance(context, Root):
                if has_permission(EDIT, context, request):
                    actions['context'].append(dict(title='Rename', url=request.resource_url(context, 'rename')))
                    actions['context'].append(dict(title='Delete', url=request.resource_url(context, 'delete')))
            if isinstance(context, Folder):
                if has_permission(VIEW, context, request):
                    actions['context'].append(dict(title='Manage contents', url=request.resource_url(context, 'contents')))
                if has_permission(ADD, context, request):
                    for item in getattr(context, '_allowed_child_types', []):
                        actions['add'].append(dict(title=item.capitalize(), url=request.resource_url(context, 'add', item)))
                if not isinstance(context, Root):
                    if has_permission(SET_ROLES, context, request):
                        actions['context'].append(dict(title='Local roles', url=request.resource_url(context, 'local_roles')))
            if isinstance(context, Content):
                actions['context'].append(dict(title='History', url=request.resource_url(context, 'history')))
                for transition in context.get_pub_workflow_transitions():
                    tname = transition['name']
                    actions['context'].append(dict(title=tname.capitalize(), url=request.resource_url(context, 'workflow_transition', tname)))
                if not context.in_trash(): actions['context'].append(dict(title='Comment', url=request.resource_url(context, 'comment')))

        actions['global'].append(dict(title='Advanced search', url=request.resource_url(root, 'advanced_search_form')))
        actions['global'].append(dict(title='Trash', url=request.resource_url(root, 'trash', '')))

        users = root['users']
        if has_permission(VIEW, users, request):
            actions['global'].append(dict(title='Manage users', url=request.resource_url(users)))
        if context._object_type == 'user collection':
            if has_permission(ADD, context, request):
                actions['add'].append(dict(title='User', url=request.resource_url(context, 'add')))
        groups = root['groups']
        if has_permission(VIEW, groups, request):
            actions['global'].append(dict(title='Manage groups', url=request.resource_url(groups)))
        if context._object_type == 'group collection':
            if has_permission(ADD, context, request):
                actions['add'].append(dict(title='Group', url=request.resource_url(context, 'add')))

        actions['global'].append(dict(title='Change my password', url=request.resource_url(root, 'my_password')))
        actions['global'].append(dict(title='Log out', url=request.resource_url(root, 'logout')))
    else:
        actions['global'].append(dict(title='Log in', url=request.resource_url(root, 'login')))

# FIXME: is the notion of a current item even relevent with the new dropdown menus?
#    current_url = request.url
#    # Strip query string, if present
#    if '?' in current_url:
#        current_url = current_url[:current_url.index('?')]
#    done = False
#    for items in actions.values():
#        for action in items:
#            if action['url'] == current_url:
#                action['current'] = True
#                done = True
#                break
#        if done: break
    return actions

def get_crumbtrail(context, request):
    crumbs = []
    obj = context
    while obj:
        crumb = dict(title=obj.title, url=request.resource_url(obj))
        obj = obj.__parent__
        if not obj: crumb['title'] = 'Home'
        crumbs.insert(0, crumb)
    return crumbs

def common_view(context, request):
    data = {}
    # FIXME: for easier customization, make master template path a setting in .ini file?  Or maybe better, have some way to register a custom common_view()?
    data['master_template'] = get_renderer('templates/master.pt').implementation()
    data['page_title'] = ""
    data['date_format'] = "%b %d, %Y"
    data['datetime_format'] = "%b %d, %Y %I:%M %p %Z"
    data['actions'] = get_actions(context, request)
    data['crumbtrail'] = get_crumbtrail(context, request)
    data['pagination'] = ""
    data['authenticated_userid'] = security.authenticated_userid(request)
    return data

# This is the original version of folder_view() before all the new Folder attributes to customize the view.
#def folder_view(context, request):
#    # Return a page of child objects.
#    data = common_view(context, request)
#    if context.is_ordered():
#        data['items'] = context.get_viewable_ordered_children()
#    else:
#        (page, per_page, skip) = get_pagination_parms(request)
#        result = context.get_viewable_children_and_total(sort=[('_created', -1)], skip=skip, limit=per_page)
#        data['items'] = result['items']
#        if result['total'] > per_page:
#            data['pagination'] = render_pagination(request, page, per_page, result['total'])
#    return data

def folder_view(context, request):
    if context.view_style == 'display_specific_child':
        name = context.specific_child_name
        child = context.get_viewable_child(name)
        if child:
            return render_view_to_response(child, request, secure=False)
        else:
            return HTTPNotFound("%s not found" % name)
    elif context.view_style == 'redirect_first_viewable':
        if context.is_ordered():
            children = context.get_viewable_ordered_children()
        else:
            children = context.get_viewable_sorted_children(limit=1)
        if children:
            return HTTPFound(location=request.resource_url(children[0]))
        # If not child, fall thru to default (which will display a page saying the folder is empty).
    elif context.view_style == 'use_template':
        data = common_view(context, request)
        # FIXME: should template_name include "templates/"?
        return render_to_response('templates/'+context.template_name, data, request=request)
    elif context.view_style == 'use_view':
        return render_view_to_response(context, request, name=context.view_name, secure=False)
        
    # Default case: context.view_style == 'list_children'
    # Return a page of child objects.
    data = common_view(context, request)
    data['intro'] = context.child_list_settings['intro']
    data['outro'] = context.child_list_settings['outro']

    list_item_style = context.child_list_settings['list_item_style']
    list_item_fields = ['title']
    if list_item_style == 'title_description':
        list_item_fields.append('description')
    elif list_item_style == 'title_date':
        list_item_fields.append('date')
    elif list_item_style == 'title_date_description':
        list_item_fields.append('date')
        list_item_fields.append('description')
    elif list_item_style == 'title_description_date':
        list_item_fields.append('description')
        list_item_fields.append('date')
    data['list_item_fields'] = list_item_fields
    display_date = context.child_list_settings['display_date']
    if display_date=='_other': display_date = context.child_list_settings['other_display_date']
    data['display_date'] = display_date

    if context.is_ordered():
        data['items'] = context.get_viewable_ordered_children()
    else:
        (page, per_page, skip) = get_pagination_parms(request)
        result = context.get_viewable_sorted_children_and_total(skip=skip, limit=per_page)
        data['items'] = result['items']
        if (page > 1) and context.child_list_settings['intro_outro_first_page_only']:
            data['intro'] = ''
            data['outro'] = ''
        if result['total'] > per_page:
            data['pagination'] = render_pagination(request, page, per_page, result['total'])
    return render_to_response('templates/folder_view.pt', data, request=request)

def search(context, request):
    data = common_view(context, request)
    data['page_title'] = "Search results"
    query = request.GET.get('query', '').strip()
    data['query'] = query
    if not query: return data
    (page, per_page, skip) = get_pagination_parms(request)
    result = context.search(fulltext=query, start=skip, size=per_page, highlight_fields=['other_text'], viewable_only=True)
    total_items = result['total']
    data['items'] = result['items']
    data['total_items'] = total_items
    data['start_num'] = (per_page * (page-1)) + 1
    if total_items > per_page:
        data['pagination'] = render_pagination(request, page, per_page, total_items)
    return data

def advanced_search_form(context, request):
    # Use deform to generate and handle form.
    object_types = context._content_type_factories.keys()
    object_types.sort()
    pub_states = acl_by_state.keys()
    pub_states.sort()
    def validate_path(path):
        try:
            context.find_resource(path)
        except KeyError:
            return "Invalid or non-existant path."
        return True
    schema = colander.SchemaNode(colander.Mapping())
    schema.add(colander.SchemaNode(colander.String(), name='fulltext', title='Full text', missing='', widget=widgets.get_wide_text_widget(), description="Search the full text of content.  Queries support wildcards and boolean expressions."))
    schema.add(colander.SchemaNode(colander.String(), name='title', title='Title', missing='', widget=widgets.get_wide_text_widget(), description="Search titles only.  Queries support wildcards and boolean expressions."))
    schema.add(colander.SchemaNode(colander.String(), name='description', title='Description', missing='', widget=widgets.get_wide_text_widget(), description="Search descriptions only.  Queries support wildcards and boolean expressions."))
    schema.add(colander.SchemaNode(colander.String(), name='__name__', title='Name', missing='', widget=widgets.get_wide_text_widget(), description="Search for objects with a specific name.  Note that the name must match exactly (wildcards and boolean expressions are not supported)."))
    schema.add(colander.SchemaNode(colander.String(), name='path', title='Path', missing='', widget=widgets.get_wide_text_widget(), description="To restrict the search to a specific portion of the content tree, enter a path here (should start with a slash character).", validator=colander.Function(validate_path)))
    schema.add(colander.SchemaNode(deform.Set(allow_empty=True), name='_object_type', title='Types', widget=deform.widget.CheckboxChoiceWidget(values=[(x,x) for x in object_types]), missing=[], description="To restrict the search to specific content types, select them here.  If you don't want to filter by type, simply leave all types unchecked."))
    schema.add(colander.SchemaNode(deform.Set(allow_empty=True), name='_pub_state', title='States', widget=deform.widget.CheckboxChoiceWidget(values=[(x,x) for x in pub_states]), missing=[], description="To restrict the search to specific publication states, select them here.  If you don't want to filter by state, simply leave all states unchecked."))

    data = common_view(context, request)
    data['page_title'] = "Advanced search form"
    form = deform.Form(schema, buttons=('search',))
    data['deform_resources'] = form.get_widget_resources()
    if 'search' in request.params:
        appstruct = {}
        try:
            appstruct = form.validate(request.params.items())
        except deform.ValidationFailure, e:
            data['form'] = e.render()
            request.session.flash("Please review the validation errors highlighted below.", 'error')
            return data
        return HTTPFound(location=request.resource_url(context, 'advanced_search_results', query=dict(appstruct)))
    data['form'] = form.render()
    return data

# FIXME: check for POST and handle batch deletes and workflow transitions
def advanced_search_results(context, request):
    data = common_view(context, request)
    csrf_token = request.session.get_csrf_token()
    data['csrf_token'] = csrf_token
    data['page_title'] = "Advanced search results"
    fulltext = request.params.get('fulltext', '').strip()
    title = request.params.get('title', '').strip()
    description = request.params.get('description', '').strip()
    __name__ = request.params.get('__name__', '').strip()
    _object_type = request.params.getall('_object_type')
    _pub_state = request.params.getall('_pub_state')
    path_id = None
    path = request.params.get('path', '').strip()
    if path:
        try:
            path_id = context.find_resource(path)._id
        except KeyError:
            path_id = None
            request.session.flash("Invalid path: %s" % path, 'error')

    data['fulltext'] = fulltext
    data['title'] = title
    data['description'] = description
    data['__name__'] = __name__
    data['path'] = path
    data['_object_type'] = _object_type
    data['_pub_state'] = _pub_state

    # Note that we expect the sort value to be an elasticsearch-style
    # sort string (for example, "_modified:desc" or "_object_type,_created:desc")
    sort = request.params.get('sort', '').strip() or None
    data['sort'] = sort

    (page, per_page, skip) = get_pagination_parms(request)
    result = context.search(fulltext=fulltext, title=title, description=description, __name__=__name__, _object_type=_object_type, _pub_state=_pub_state, path_id=path_id, start=skip, size=per_page, viewable_only=False, sort=sort)
    total_items = result['total']
    data['items'] = result['items']
    data['total_items'] = total_items
    data['start_num'] = (per_page * (page-1)) + 1
    if total_items > per_page:
        data['pagination'] = render_pagination(request, page, per_page, total_items)

    # Build up a (relatively) friendly string describing the search parameters.
    summary_parts = []
    if fulltext: summary_parts.append("full text = %s" % fulltext)
    if title: summary_parts.append("title = %s" % title)
    if description: summary_parts.append("description = %s" % description)
    if __name__: summary_parts.append("name = %s" % __name__)
    if path: summary_parts.append("path = %s" % path)
    if _object_type: summary_parts.append("type = %s" % ', '.join(_object_type))
    if _pub_state: summary_parts.append("state = %s" % ', '.join(_pub_state))
    if summary_parts: summary = "; ".join(summary_parts)
    else: summary = "everything"
    data['summary'] = "You searched for "+summary
    return data

def add_object(context, request):
    object_type = request.subpath[0]
    if object_type not in context._allowed_child_types:
        raise ValueError, "This %s does not allow child objects of type %s." % (context._object_type, object_type)
    return edit_form(context, request, cls=request.root.get_content_factory(object_type))

# For flexibility/reusability edit_form() supports 4 optional callback parms:
# success_redirect(context, request)
# Should return the url to redirect to upon successfully editing the object.
# "context" is the object that was successfully saved.
#
# morph_schema(context, request, schema)
# pre_save(context, request, appstruct)
# post_save(context, request, appstruct)
# The return value of all 3 is ignored.
# morph_schema() should modify the schema in-place.
#
# For morph_schema(), "context" is the same context object passed to edit_form(),
# the parent if adding or the object itself if editing..
# For pre_save() and post_save(), "context" is always the object about-to-be/just saved.
def edit_form(context, request, cls=None, buttons=None, success_redirect=None, morph_schema=None, pre_save=None, post_save=None):
    if buttons is None:
        buttons = (deform.Button(name='save', title='Save'), deform.Button(name='view', title='Save & View'))
    def default_success_redirect(context, request):    
        if 'view' in request.POST:
            return request.resource_url(context)
        else:
            return request.resource_url(context, 'edit')
    if success_redirect is None:
        success_redirect = default_success_redirect

    data = common_view(context, request)
    if cls:
        mode = "add"
        obj = None
    else:
        mode = "edit"
        obj = context
        cls = obj.__class__
    data['mode'] = mode
    data['page_title'] = "%s %s" % (mode.capitalize(), cls._object_type)
    schema = cls.get_class_schema(request)
    csrf_token = request.session.get_csrf_token()
    schema.children.append(colander.SchemaNode(colander.String(), name='csrf_token', widget=deform.widget.HiddenWidget(), default=csrf_token, missing=''))

    tmpstore = MongoFileUploadTempStore(request)
    TMP_FILES_MAPPING = '_tmp_files_mapping'
    schema.children.append(colander.SchemaNode(colander.String(), name=TMP_FILES_MAPPING, widget=deform.widget.HiddenWidget(), missing=''))

    if mode == 'add':
        def validate_name(name):
            return context.veto_child_name(name) or True
        schema.children.insert(0, colander.SchemaNode(colander.String(), name='name', title=cls._name_title, validator=colander.Function(validate_name), widget=deform.widget.TextInputWidget(size=NAME_INPUT_SIZE)))

    if morph_schema:
        morph_schema(context, request, schema)

    form = deform.Form(schema, buttons=buttons)
    data['deform_resources'] = form.get_widget_resources()

    appstruct = {}
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        tmpstore.update_file_mapping_from_serialized(request.POST[TMP_FILES_MAPPING])
        try:
            appstruct = form.validate(request.POST.items())
        except deform.ValidationFailure, e:
            e.cstruct[TMP_FILES_MAPPING] = tmpstore.serialize_file_mapping()
            data['form'] = e.render()
            request.session.flash("Please review the validation errors highlighted below.", 'error')
            return data
        is_content = issubclass(cls, Content)
        if mode == 'add':
            name = appstruct['name']

            if is_content:
                obj = command.create(request, context, cls, name, appstruct, pre_save=pre_save)
            else:
                obj = cls(request)
                obj.set_appstruct(appstruct)
                if pre_save: pre_save(obj, request, appstruct)
                context.add_child(name, obj)

            msg = "Added %s." % obj._object_type
        else:
            msg = "Changes saved."
            if is_content:
                changed = command.edit(request, obj, appstruct, pre_save=pre_save)
                if not changed: msg = "You didn't change anything."
            else:
                obj.set_appstruct(appstruct)
                if pre_save: pre_save(obj, request, appstruct)
                obj.save()

        if post_save: post_save(obj, request, appstruct)
        request.session.flash(msg, 'info')
        return HTTPFound(location=success_redirect(obj, request))
    else: # GET request
        if mode == 'edit':
            appstruct = obj.get_appstruct()
            appstruct[TMP_FILES_MAPPING] = tmpstore.serialize_file_mapping()
    data['form'] = form.render(appstruct)
    return data

# Really delete an object (for good).
def delete_object(context, request):
    if 'cancel' in request.POST:
        return HTTPFound(location=request.resource_url(context))
    csrf_token = request.session.get_csrf_token()
    if 'submit' in request.POST:
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        parent = context.__parent__
        msg = "Deleted %s named %s." % (context._object_type, context.__name__)
        parent.delete_child(context.__name__)
        request.session.flash(msg, 'info')
        return HTTPFound(location=request.resource_url(parent))
    data = common_view(context, request)
    data['csrf_token'] = csrf_token
    data['page_title'] = "Confirm deletion"
    return data

# Move a content object into the trash.
def trash_object(context, request):
    if 'cancel' in request.POST:
        return HTTPFound(location=request.resource_url(context))
    csrf_token = request.session.get_csrf_token()
    if 'submit' in request.POST:
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        parent = context.__parent__
        msg = "Deleted %s named %s." % (context._object_type, context.__name__)
        command.trash_object(request, context)
        request.session.flash(msg, 'info')
        return HTTPFound(location=request.resource_url(parent))
    data = common_view(context, request)
    data['csrf_token'] = csrf_token
    data['page_title'] = "Confirm delete"
    return data

def rename_object(context, request):
    data = common_view(context, request)
    data['page_title'] = "Rename form"
    parent = context.__parent__
    schema = colander.SchemaNode(colander.Mapping())
    csrf_token = request.session.get_csrf_token()
    schema.children.append(colander.SchemaNode(colander.String(), name='csrf_token', widget=deform.widget.HiddenWidget(), default=csrf_token, missing=''))
    def validate_name(name):
        return parent.veto_child_name(name) or True
    schema.children.append(colander.SchemaNode(colander.String(), name='newname', title='New name', validator=colander.Function(validate_name), widget=deform.widget.TextInputWidget(size=NAME_INPUT_SIZE), default=context.__name__))

    form = deform.Form(schema, buttons=('rename',))
    data['deform_resources'] = form.get_widget_resources()

    appstruct = {}
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        try:
            appstruct = form.validate(request.POST.items())
        except deform.ValidationFailure, e:
            data['form'] = e.render()
            request.session.flash("Please review the validation errors highlighted below.", 'error')
            return data
        newname = appstruct['newname']
        msg = "Renamed \"%s\" to \"%s\"." % (context.__name__, newname)
        if isinstance(context, Content):
            command.rename_object(request, context, newname)
        else:
            parent.rename_child(context.__name__, newname)
        request.session.flash(msg, 'info')
        return HTTPFound(location=request.resource_url(parent, newname, ''))
    data['form'] = form.render(appstruct)
    return data

def get_pagination_parms(request, default_per_page=20):
    try:
        page = int(request.GET.get('page'))
    except:
        page = 1
    try:
        per_page = int(request.GET.get('per_page'))
    except:
        per_page = default_per_page
    skip = (page-1) * per_page
    return (page, per_page, skip)

def render_pagination(request, page, per_page, total_items):
    total_pages = total_items / per_page
    if total_items % per_page: total_pages += 1
    query_dict = {}
    query_dict.update(request.GET)
    def get_page_url(page_num):
        query_dict['page'] = page_num
        return request.resource_url(request.context, request.view_name, query=query_dict)
    return render('templates/pagination.pt',
                  dict(page=page, per_page=per_page, total_items=total_items, total_pages=total_pages, get_page_url=get_page_url, significant_page_nums=get_significant_page_nums(total_pages, page)),
                  request=request)

def get_significant_page_nums(total_pages, page):
    sig = []
    if total_pages < 14:
        # 13 or fewer pages, so all are significant.
        for x in range(1, total_pages+1):
            sig.append(x)
    elif page < 8:    
        # Significant pages are 1-10 and the last two.
        for x in range(1, 11):
            sig.append(x)
        sig.append(None)
        sig.append(total_pages-1)
        sig.append(total_pages)
    else:
        # Significant pages are of course 1 and 2.... but depending on how close the current page is to the last page, we may or may not need a second None/ellipsis value.
        sig.append(1)
        sig.append(2)
        sig.append(None)
        if total_pages - page < 7:
            # Current page is close to the end, so no second ellipsis needed.
            for x in range(total_pages-9, total_pages+1):
                sig.append(x)
        else:
            # Current page is far enough from the end that we need a second ellipsis.
            for x in range(page-3, page+4):
                sig.append(x)
            sig.append(None)
            sig.append(total_pages-1)
            sig.append(total_pages)
    return sig

def gridfs_file_view(context, request):
    return dbutil.serve_gridfs_file(context)

def serve_file(context, request):
    # Handle urls of the form: /serve_file/gridfs_id
    return dbutil.serve_gridfs_file_for_id(request, ObjectId(request.subpath[0]))

# @view_config(context='cms.resources.Content', name="external_link_list.js")
# def external_link_list(context, request, images_only=False):
#     # Generate a javascript file for TinyMCE
#     # Used in Link/Image dialog box.
#     # See http://wiki.moxiecode.com/index.php/TinyMCE:Configuration/external_image_list_url and http://wiki.moxiecode.com/index.php/TinyMCE:Configuration/external_link_list_url
#     array_name = "tinyMCELinkList"
#     if images_only: array_name = "tinyMCEImageList"
#     lines = []
#     lines.append("var %s = new Array();" % array_name)
#     count = 0
#     for file in context.get_files_for_attribute('attachments'):
#         if images_only and not file.content_type.startswith('image'): continue
#         lines.append('%s[%s] = ["%s", "%s"];' % (array_name, count, file.name, file.name))
#         count += 1
#     response = Response('\n'.join(lines))
#     response.content_type = 'text/javascript'
#     return response
# 
# @view_config(context='cms.resources.Content', name="external_image_list.js")
# def external_image_list(context, request):
#     return external_link_list(context, request, images_only=True)

def collection_contents_view(context, request, default_sort=[]):
    """ Return data for collection management page.
    default_sort - If specified, a list of mongo sort tuples.
    Prefix the sort name with a minus sign for descending (example: "-_modified").
    """
    data = common_view(context, request)

    req_sort = request.GET.get('sort', '').strip()
    if req_sort:
        if req_sort.startswith('-'):
            sort_dir = -1
            sort_on = req_sort[1:]
        else:
            sort_dir = 1
            sort_on = req_sort
        sort = [(sort_on, sort_dir)]
    else:
        sort = default_sort
    data['sort'] = sort

    # Note: would use context.is_ordered(), but this view is used by Collection, not just Folder.
    if getattr(context, '_is_ordered', False) and not sort:
        children = context.get_ordered_children()
        data['items'] = children
        data['total_items'] = len(children)
    else:
        (page, per_page, skip) = get_pagination_parms(request)
        result = context.get_children_and_total(sort=sort, skip=skip, limit=per_page)
        data['items'] = result['items']
        data['total_items'] = result['total']
        if result['total'] > per_page:
            data['pagination'] = render_pagination(request, page, per_page, result['total'])
    return data

def folder_contents(context, request):
    csrf_token = request.session.get_csrf_token()
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        if 'rename' in request.POST:
            orignames = request.POST.getall('orignames')
            newnames = request.POST.getall('newnames')
            renames = []
            for (origname, newname) in zip(orignames, newnames):
                if origname != newname:
                    child = context.get_child(origname)
                    if child:
                        if not has_permission(EDIT, child, request):
                            raise HTTPForbidden("You don't have permission to rename %s." % origname)
                        renames.append((origname, newname))
            try:
                num = command.rename_children(request, context, renames)
                msg = "Renamed %s %s." % (num, (num==1 and "item") or "items")
                request.session.flash(msg, 'info')
            except Veto, e:
                request.session.flash(str(e), 'error')

        elif 'delete' in request.POST:
            names = request.POST.getall('names')
            if names:
                children_to_trash = []
                for name in names:
                    child = context.get_child(name)
                    if child:
                        if has_permission(EDIT, child, request):
                            children_to_trash.append(child)
                        else:
                            raise HTTPForbidden("You don't have permission to delete %s." % name)
                num = command.trash_children(request, context, children_to_trash)
                msg = "Deleted %s %s." % (num, (num==1 and "item") or "items")
                request.session.flash(msg, 'info')
            else:
                request.session.flash("You didn't select any items to delete.", 'warn')
        elif 'copy' in request.POST:
            names = request.POST.getall('names')
            if names:
                ids = []
                for name in names:
                    child = context.get_child(name)
                    if child:
                        ids.append(child._id)
                num = len(ids)
                request.session[PASTE_BUFFER] = dict(op='copy', ids=ids)
                msg = "Put %s %s in copy buffer." % (num, (num==1 and "item") or "items")
                request.session.flash(msg, 'info')
            else:
                request.session.flash("You didn't select any items to copy.", 'warn')
        elif 'cut' in request.POST:
            names = request.POST.getall('names')
            if names:
                ids = []
                for name in names:
                    child = context.get_child(name)
                    if child:
                        if not has_permission(EDIT, child, request):
                            raise HTTPForbidden("You don't have permission to delete %s." % name)
                        ids.append(child._id)
                num = len(ids)
                request.session[PASTE_BUFFER] = dict(op='cut', ids=ids)
                msg = "Put %s %s in cut buffer." % (num, (num==1 and "item") or "items")
                request.session.flash(msg, 'info')
            else:
                request.session.flash("You didn't select any items to cut.", 'warn')
        elif 'paste' in request.POST:
            if not has_permission(ADD, context, request):
                raise HTTPForbidden("You don't have permission to add content here.")
            pbuffer = request.session.get(PASTE_BUFFER, {})
            op = pbuffer['op']
            ids = pbuffer['ids']
            root = context.find_root()
            objects_to_paste = []
            trash = request.root['trash']
            orig_parent = None
            error = None
            clear_paste_buffer = False
            for _id in ids:
                obj = root.get_content_by_id(_id)
                if obj:
                    parent = obj.__parent__
                    parent_id = parent._id
                    if orig_parent is None:
                        orig_parent = parent
                    elif orig_parent._id != parent_id:
                        error = "It looks like some objects have moved since being placed in your paste buffer.  Your paste buffer has been cleared."
                        clear_paste_buffer = True
                        break
                    if parent_id == 'trash':
                        trash.dememento_child(obj)
                    objects_to_paste.append(obj)

            num = 0
            if not error:
                try:
                    if op == 'copy':
                        num = command.copy_children(request, orig_parent, context, objects_to_paste)
                    elif op == 'cut':
                        num = command.move_children(request, orig_parent, context, objects_to_paste)
                except Veto, e:
                    error = str(e)

            if error:
                request.session.flash(error, 'error')
            else:
                msg = "Pasted %s %s." % (num, (num==1 and "item") or "items")
                request.session.flash(msg, 'info')
                if (op == 'cut') or (not objects_to_paste):
                    clear_paste_buffer = True

            if clear_paste_buffer: del request.session[PASTE_BUFFER]

        elif ('reorder_top' in request.POST) or ('reorder_bottom' in request.POST) or ('reorder_up' in request.POST) or ('reorder_down' in request.POST):
            names = request.POST.getall('names')
            if names:
                target = None
                delta = None
                if 'reorder_top' in request.POST:
                    target = 'top'
                elif 'reorder_bottom' in request.POST:
                    target = 'bottom'
                elif 'reorder_up' in request.POST:
                    target = 'up'
                elif 'reorder_down' in request.POST:
                    target = 'down'
                if target in ('up', 'down'):
                    raw_delta = request.POST.get('delta', '').strip()
                    try:
                        delta = int(raw_delta)
                    except:
                        delta = None
                    if (not delta) or (delta < 1):
                        request.session.flash("Number to move %s should be a positive integer (you entered \"%s\")." % (target, raw_delta), 'error')
                        target = None
                if target:
                    if not has_permission(EDIT, context, request):
                        raise HTTPForbidden("You don't have permission to reorder children in this folder.")
                    reordered_names = command.reorder_children(request, context, names, target, delta)
                    num = len(reordered_names)
                    msg = "Reordered %s %s." % (num, (num==1 and "item") or "items")
                    request.session.flash(msg, 'info')
            else:
                request.session.flash("You didn't select any items to reorder.", 'warn')

    default_sort = []
    if not context.is_ordered(): default_sort = context.get_default_sort()
    data = collection_contents_view(context, request, default_sort=default_sort)
    data['can_paste'] = request.session.get(PASTE_BUFFER, None) and not context.in_trash()
    data['csrf_token'] = csrf_token
    data['page_title'] = "Manage contents"
    return data

def add_user(context, request):
    def morph_schema(context, request, schema):
        schema.children.append(colander.SchemaNode(colander.String(), name='password', title='Password', widget=deform.widget.CheckedPasswordWidget(size=20), missing='', description="If left blank, a random password will be generated."))
        schema.children.append(colander.SchemaNode(colander.Boolean(), name='mail_password', title='Mail password', missing=False, description="If checked, a message will be sent to the user with their username, password and a link to the login form."))
    def pre_save(context, request, appstruct):
        password = appstruct['password'] or generate_random_password()
        context.set_password(password)
        context._password = password
    def post_save(context, request, appstruct):
        if appstruct['mail_password']:
            context.mail_password(context._password)
    return edit_form(context, request, cls=User, morph_schema=morph_schema, pre_save=pre_save, post_save=post_save)

def user_collection_view(context, request):
    csrf_token = request.session.get_csrf_token()
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        if 'delete' in request.POST:
            names = request.POST.getall('names')
            if names:
                for name in names:
                    child = context.get_child(name)
                    if not has_permission(EDIT, child, request):
                        raise HTTPForbidden("You don't have permission to delete %s." % name)
                num = 0
                for name in names:
                    num += context.delete_child(name)
                msg = "Deleted %s %s." % (num, (num==1 and "item") or "items")
                request.session.flash(msg, 'info')
            else:
                request.session.flash("You didn't select any items to delete.", 'warn')
    data = collection_contents_view(context, request, default_sort=[('__name__', 1)])
    data['csrf_token'] = csrf_token
    return data

def user_password(context, request):
    data = common_view(context, request)
    data['page_title'] = "Set password"
    schema = colander.SchemaNode(colander.Mapping())
    csrf_token = request.session.get_csrf_token()
    schema.children.append(colander.SchemaNode(colander.String(), name='csrf_token', widget=deform.widget.HiddenWidget(), default=csrf_token, missing=''))
    schema.children.append(colander.SchemaNode(colander.String(), name='password', title='Password', widget=deform.widget.CheckedPasswordWidget(size=20)))
    schema.children.append(colander.SchemaNode(colander.Boolean(), name='mail_password', title='Mail password', missing=False))

    form = deform.Form(schema, buttons=('set password',))
    data['deform_resources'] = form.get_widget_resources()

    appstruct = {}
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        try:
            appstruct = form.validate(request.POST.items())
        except deform.ValidationFailure, e:
            data['form'] = e.render()
            request.session.flash("Please review the validation errors highlighted below.", 'error')
            return data
        msg = "Changed password for %s." % context.__name__
        password = appstruct['password']
        context.set_password(password)
        context.save()
        if appstruct['mail_password']:
            context.mail_password(password)
        request.session.flash(msg, 'info')
        return HTTPFound(location=request.resource_url(context))
    data['form'] = form.render(appstruct)
    return data

def group_collection_view(context, request):
    csrf_token = request.session.get_csrf_token()
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        if 'delete' in request.POST:
            names = request.POST.getall('names')
            if names:
                for name in names:
                    child = context.get_child(name)
                    if not has_permission(EDIT, child, request):
                        raise HTTPForbidden("You don't have permission to delete %s." % name)
                num = 0
                for name in names:
                    num += context.delete_child(name)
                msg = "Deleted %s %s." % (num, (num==1 and "item") or "items")
                request.session.flash(msg, 'info')
            else:
                request.session.flash("You didn't select any items to delete.", 'warn')
    data = common_view(context, request)
    data['csrf_token'] = csrf_token
    return data

def add_group(context, request):
    def success_redirect(context, request):    
        return request.resource_url(context.__parent__)
    return edit_form(context, request, cls=Group, buttons=('save',), success_redirect=success_redirect)

RANDOM_GREETINGS = (
    'Welcome %s!',
    'Hello %s!',
    'Howdy %s!',
    'Greetings %s!',
    'Nice to see you, %s!',
    'Well good morning, %s!',
    'Hi there, %s!',
    "You're looking sharp today, %s!",
    "I'm ready, %s!",
    "Let's go, %s!",
    "I've got a good feeling about today, %s!",
)
RANDOM_FAREWELLS = (
    'Goodbye %s!',
    'Farewell %s!',
    'Later %s!',
    'So long %s!',
    'See you soon, %s!',
    'See you around, %s!',
    'See you next time, %s!',
    'Take it easy, %s!',
    "Good job, %s!",
    "Leaving so soon, %s?",
    "I've had enough too, %s.  Let's call it a day.",
    u"\xa1Adi\xf3s, %s!",
    "Auf Wiedersehen, %s!",
)

def login(context, request):
    forbidden_msg = None
    if isinstance(context, HTTPForbidden):
        forbidden_msg = context.message
        context = request.context
    data = common_view(context, request)
    data['context'] = context
    data['page_title'] = 'Login Form'
    login_url = request.resource_url(find_root(context), 'login')
    data['login_url'] = login_url
    referrer = request.url
    if referrer == login_url:
        # never use the login form itself as came_from
        referrer = '/'
    else:
        request.session.flash(forbidden_msg or "Permission denied.", 'error')
    came_from = request.params.get('came_from', referrer)
    data['came_from'] = came_from
    username = request.params.get('username', '').strip()
    if request.method == 'POST' and request.params.get('login-submitted'):
        password = request.params.get('password', '').strip()
        user = context.get_user(username)
        if user and user.check_password(password):
            headers = security.remember(request, username)
            user.set_last_logged_in()
            user.save(set_modified=False)
            msg = random.choice(RANDOM_GREETINGS) % (user.firstname or user.__name__)
            #msg = 'Logged in.  %s" % msg
            request.session.flash(msg, 'info')
            return HTTPFound(location = came_from, headers = headers)
        request.session.flash("Log in failed.", 'error')
        request.response.status_int = 401 # Unauthorized
    data['username'] = username
    return data

def logout(context, request):
    user = context.get_current_user()
    headers = security.forget(request)
    msg = random.choice(RANDOM_FAREWELLS) % (user.firstname or user.__name__)
    #msg = 'Logged out.  %s" % msg
    request.session.flash(msg, 'info')
    return HTTPFound(location=request.resource_url(context), headers=headers)

def my_password(context, request):
    data = common_view(context, request)
    data['page_title'] = "Change my password"
    schema = colander.SchemaNode(colander.Mapping())
    csrf_token = request.session.get_csrf_token()
    schema.children.append(colander.SchemaNode(colander.String(), name='csrf_token', widget=deform.widget.HiddenWidget(), default=csrf_token, missing=''))
    schema.children.append(colander.SchemaNode(colander.String(), name='password', title='Password', widget=deform.widget.CheckedPasswordWidget(size=20)))

    form = deform.Form(schema, buttons=('set password',))
    data['deform_resources'] = form.get_widget_resources()

    appstruct = {}
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        try:
            appstruct = form.validate(request.POST.items())
        except deform.ValidationFailure, e:
            data['form'] = e.render()
            request.session.flash("Please review the validation errors highlighted below.", 'error')
            return data
        msg = "Password changed."
        password = appstruct['password']
        user = context.get_current_user()
        user.set_password(password)
        user.save()
        request.session.flash(msg, 'info')
        return HTTPFound(location=request.resource_url(context))
    data['form'] = form.render(appstruct)
    return data

def reset_password(context, request):
    data = common_view(context, request)
    data['page_title'] = "Reset forgotten password"
    schema = colander.SchemaNode(colander.Mapping())
    csrf_token = request.session.get_csrf_token()
    schema.children.append(colander.SchemaNode(colander.String(), name='csrf_token', widget=deform.widget.HiddenWidget(), default=csrf_token, missing=''))
    schema.children.append(colander.SchemaNode(colander.String(), name='name_or_email', title='Username or e-mail'))

    form = deform.Form(schema, buttons=('reset password',))
    data['deform_resources'] = form.get_widget_resources()

    appstruct = {}
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        try:
            appstruct = form.validate(request.POST.items())
        except deform.ValidationFailure, e:
            data['form'] = e.render()
            msg = "Please review the validation errors highlighted below."
            request.session.flash(msg, 'error')
            return data
        name_or_email = appstruct['name_or_email']
        user = context.get_user(name_or_email) or context.get_user_by_email(name_or_email)
        if user:
            if user.email: 
                password = generate_random_password()
                user.set_password(password)
                user.save()
                user.mail_password(password)
                msg = "Password was reset.  Check your e-mail for the new password."
                request.session.flash(msg, 'info')
                return HTTPFound(location=request.resource_url(context))
            else:
                msg = "Could not send email for the specified user.  Ask the site admin for help."
                request.session.flash(msg, 'error')
        else:
            msg = "No matching user found."
            request.session.flash(msg, 'error')
    data['form'] = form.render(appstruct)
    return data

# Handle urls like /foo/workflow_transition/publish
def workflow_transition(context, request):
    data = common_view(context, request)
    transition = request.subpath[0]
    data['transition'] = transition
    data['page_title'] = "%s %s" % (transition.capitalize(), context._object_type)

    schema = colander.SchemaNode(colander.Mapping())
    csrf_token = request.session.get_csrf_token()
    schema.children.append(colander.SchemaNode(colander.String(), name='csrf_token', widget=deform.widget.HiddenWidget(), default=csrf_token, missing=''))
    schema.children.append(colander.SchemaNode(colander.String(), name='comment', widget=widgets.get_wide_textarea_widget(rows=5)))
    if isinstance(context, Folder):
        schema.children.append(colander.SchemaNode(colander.Boolean(), name='recurse', title='Recursively %s children?' % transition, missing=False))

    form = deform.Form(schema, buttons=(transition,))
    data['deform_resources'] = form.get_widget_resources()

    appstruct = {}
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        try:
            appstruct = form.validate(request.POST.items())
        except deform.ValidationFailure, e:
            data['form'] = e.render()
            request.session.flash("Please review the validation errors highlighted below.", 'error')
            return data
        comment = appstruct['comment']
        recurse = appstruct.get('recurse', False)
        command.transition(request, context, transition, comment, recurse)
        msg = "%s transition complete.  Now in the %s state." % (transition.capitalize(), context.get_pub_state())
        request.session.flash(msg, 'info')
        return HTTPFound(location = request.resource_url(context))
    data['form'] = form.render(appstruct)
    return data

def comment(context, request):
    data = common_view(context, request)
    data['page_title'] = "Comment on %s" % context._object_type

    schema = colander.SchemaNode(colander.Mapping())
    csrf_token = request.session.get_csrf_token()
    schema.children.append(colander.SchemaNode(colander.String(), name='csrf_token', widget=deform.widget.HiddenWidget(), default=csrf_token, missing=''))
    schema.children.append(colander.SchemaNode(colander.String(), name='comment', widget=widgets.get_wide_textarea_widget(rows=5)))

    form = deform.Form(schema, buttons=(deform.Button(name='save', title='Comment'),))
    data['deform_resources'] = form.get_widget_resources()

    appstruct = {}
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        try:
            appstruct = form.validate(request.POST.items())
        except deform.ValidationFailure, e:
            data['form'] = e.render()
            request.session.flash("Please review the validation errors highlighted below.", 'error')
            return data
        comment = appstruct['comment']
        command.comment(request, context, comment)
        msg = "Comment logged."
        request.session.flash(msg, 'info')
        return HTTPFound(location = request.resource_url(context))
    data['form'] = form.render(appstruct)
    return data

def folder_local_roles(context, request):
    csrf_token = request.session.get_csrf_token()
    groups_coll = request.root['groups']
    groups = groups_coll.get_children(sort=[('__name__', 1)])
    roles = groups_coll.get_system_group_names()
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        # Build local_roles dictionary based on form data.
        local_roles = {}
        for group in groups:
            groupname = group.__name__
            role = request.POST.get('%s_role' % groupname)
            if role in roles:
                local_roles['group:%s' % groupname] = 'group:%s' % role
        context.set_local_roles(local_roles)
        msg = "Saved local roles."
        request.session.flash(msg, 'info')
        if 'view' in request.POST:
            redirect = request.resource_url(context)
        else:
            redirect = request.resource_url(context, 'local_roles')
        return HTTPFound(location=redirect)
    data = common_view(context, request)
    data['csrf_token'] = csrf_token
    data['page_title'] = "Local roles"
    data['groups'] = groups
    data['roles'] = roles 
    data['local_roles'] = context.get_local_roles()
    return data

def notfound(request):
    context = request.context
    data = common_view(context, request)
    data['page_title'] = "404 Not Found"
    data['context'] = context
    request.response.status_int = 404
    return data

def content_by_id(context, request):
    # Handle urls of the form: /content_by_id/_id
    _id = request.subpath[0]
    obj = request.root.get_content_by_id(ObjectId(_id))
    if obj:
        return HTTPFound(location=request.resource_url(obj))
    else:
        return HTTPNotFound("No data for id=%s" % _id)

def trash_contents(context, request):
    csrf_token = request.session.get_csrf_token()
    is_superuser = 'group:superuser' in security.effective_principals(request)
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        if 'copy' in request.POST:
            names = request.POST.getall('names')
            if names:
                ids = []
                for name in names:
                    child = context.get_child(name)
                    if child:
                        ids.append(child._id)
                num = len(ids)
                request.session[PASTE_BUFFER] = dict(op='copy', ids=ids)
                msg = "Put %s %s in copy buffer." % (num, (num==1 and "item") or "items")
                request.session.flash(msg, 'info')
            else:
                request.session.flash("You didn't select any items to copy.", 'warn')
        elif 'restore' in request.POST:
            user_name = security.authenticated_userid(request)
            names = request.POST.getall('names')
            if names:
                vetoed = False
                children_to_restore = []
                for name in names:
                    child = context.get_child(name)
                    if child:
                        error = None
                        if not is_superuser:
                            trashed_by = child._memento['trashed_by']
                            if user_name != trashed_by:
                                error = "Must be %s or a superuser to restore." % trashed_by
                        if error:
                            orig_name = child._memento['orig_name']
                            request.session.flash("Cannot restore %s (%s). %s" % (orig_name, name, error), 'error')
                            vetoed = True
                        else:
                            children_to_restore.append(child)
                if not vetoed:
                    try:
                        num = command.restore_objects(request, children_to_restore)
                        msg = "Restored %s %s." % (num, (num==1 and "item") or "items")
                        request.session.flash(msg, 'info')
                    except Veto, e:
                        request.session.flash(str(e), 'error')
            else:
                request.session.flash("You didn't select any items to restore.", 'warn')
        elif 'delete' in request.POST:
            if not is_superuser:
                raise HTTPForbidden("You don't have permission to delete from the trash.")
            names = request.POST.getall('names')
            if names:
                num = 0
                for name in names:
                    num += context.delete_child(name)
                msg = "Deleted %s %s." % (num, (num==1 and "item") or "items")
                request.session.flash(msg, 'info')
            else:
                request.session.flash("You didn't select any items to delete.", 'warn')
    data = collection_contents_view(context, request, default_sort=[('_modified', -1)])
    data['csrf_token'] = csrf_token
    data['can_delete'] = is_superuser
    return data

def history_view(context, request):
    csrf_token = request.session.get_csrf_token()
    can_revert = has_permission(EDIT, context, request)
    if request.method == 'POST':
        if csrf_token != request.POST['csrf_token']:
            raise CSRFMismatch()
        history_ids = request.POST.getall('ids')
        if 'diff' in request.POST:
            if len(history_ids) in (1,2):
                return HTTPFound(location=request.resource_url(context, 'history_diffs', query=dict(ids=history_ids)))
            else:
                request.session.flash("Please select one or two items to diff.", 'warn')
        elif 'revert' in request.POST:
            if not can_revert:
                 raise HTTPForbidden("You don't have permission to revert this %s." % context._object_type)
            if len(history_ids) == 1:
                msg = "Successfully reverted."
                changed = command.revert(request, context, ObjectId(history_ids[0]))
                if not changed: msg = "Nothing would have changed."
                request.session.flash(msg, 'info')
                return HTTPFound(location=request.resource_url(context))
            else:
                request.session.flash("Please select a single item to revert to.", 'warn')
    data = common_view(context, request)
    data['page_title'] = "History"
    (page, per_page, skip) = get_pagination_parms(request)
    hc = HistoryCollection(request)
    result = hc.get_history_for_id(context._id, skip=skip, limit=per_page)
    data['items'] = result['items']
    if result['total'] > per_page:
        data['pagination'] = render_pagination(request, page, per_page, result['total'])
    data['csrf_token'] = csrf_token
    data['can_revert'] = can_revert
    data['hc'] = hc
    return data

def history_snapshot(context, request):
    history_id = request.subpath[0]
    HistoryCollection(request).apply_history(context, ObjectId(history_id))
    return render_view_to_response(context, request, secure=False)
    
# Handle urls of the form: context/edit_history_diffs/history_id
def edit_history_diffs(context, request):
    history_id = ObjectId(request.subpath[0])
    hc = HistoryCollection(request)
    history_item = hc.get_history_item(history_id)
    if not history_item: raise ValueError("Didn't find specified history record.")
    diffs = hc.get_edit_history_diffs(context, history_id)
    data = common_view(context, request)
    data['page_title'] = "History Diffs"
    data['diffs'] = diffs
    data['subtitle'] = "Changes made by %s at %s" % (history_item['user'], formatters.format_localized_datetime(request, history_item['time'], data['datetime_format']))
    return data
    
def history_diffs(context, request):
    history_ids = request.GET.getall('ids')
    history_id1 = ObjectId(history_ids[0])
    hc = HistoryCollection(request)
    history_item1 = hc.get_history_item(history_id1)
    if not history_item1: raise ValueError("Didn't find specified history record.")
    time1 = history_item1['time']
    if len(history_ids) > 1:
        history_id2 = ObjectId(history_ids[1])
        history_item2 = hc.get_history_item(history_id2)
        if not history_item2: raise ValueError("Didn't find specified history record.")
        time2 = history_item2['time']
    else:
        history_id2 = None
        time2 = context._modified
    diffs = hc.get_history_diffs(context, history_id1, history_id2)
    data = common_view(context, request)
    data['page_title'] = "History Diffs"
    data['diffs'] = diffs
    data['subtitle'] = "Changes made between %s and %s" % (formatters.format_localized_datetime(request, time1, data['datetime_format']), formatters.format_localized_datetime(request, time2, data['datetime_format']))
    return data
