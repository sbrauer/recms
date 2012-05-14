# The "Command Module" - a high level interface for operations that modify the content
# database, with history logging.
# The command module doesn't enforce any permissions (that's up to view code).
# Some command functions (particularly those that can affect several objects at once)
# may raise a Veto exception if any of the requested operations cannot be performed.
# This provides a sort of half-assed workaround for the lack of transactions we have
# with MongoDB, and tries to ensure that all commands will be history logged.
# However race conditions and programmer errors are still possible.  That's life, I suppose.
# In any case, if you care about recording history (and you should), use the command
# module functions when you need to change the content database, instead of directly
# calling destructive methods of the content objects themselves.

from resources.history import HistoryCollection
from diffutil import diff_dictionaries

def log_history(request, action, ids, **kwargs):
    HistoryCollection(request).log_history(action, ids, **kwargs)

def create(request, parent, cls, name, appstruct, pre_save=None):
    parent_id = parent._id
    parent_path = parent.resource_path()
    child = cls(request)
    child.set_appstruct(appstruct)
    if pre_save: pre_save(child, request, appstruct)
    parent.add_child(name, child)
    child_id = child._id

    log_history(request, 'create',
        ids=[child_id, parent_id],
        parent_id=parent_id,
        parent_path=parent_path,
        child_id=child_id,
        child_name=name)
    return child

def edit(request, obj, appstruct, pre_save=None):
    object_id=obj._id
    object_path=obj.resource_path()
    old_values = obj.get_schema_values()
    obj.set_appstruct(appstruct)
    if pre_save: pre_save(obj, request, appstruct)
    new_values = obj.get_schema_values()
    changes = diff_dictionaries(old_values, new_values)
    if not changes: return False
    obj.save()
    log_history(request, 'edit',
        ids=[object_id],
        object_path=object_path,
        changes=changes)
    return True

def comment(request, obj, comment):
    object_id=obj._id
    object_path=obj.resource_path()
    log_history(request, 'comment',
        ids=[object_id],
        comment=comment,
        object_path=object_path)

def transition(request, obj, transition, comment, recurse=False):
    object_id=obj._id
    object_path=obj.resource_path()
    if recurse:
        ids = list(obj.pub_workflow_transition_recursively(transition))
    else:
        ids = [object_id]
        obj.pub_workflow_transition(transition)
    log_history(request, transition,
        ids=ids,
        comment=comment,
        object_id=object_id,
        object_path=object_path,
        recurse=recurse)

def revert(request, obj, history_id):
    hc = HistoryCollection(request)
    history_item = hc.get_history_item(history_id)
    history_time = history_item['time']
    object_id=obj._id
    object_path=obj.resource_path()
    old_values = obj.get_schema_values()
    hc.apply_history(obj, history_id)
    new_values = obj.get_schema_values()
    changes = diff_dictionaries(old_values, new_values)
    if not changes: return False
    obj.save()
    log_history(request, 'revert',
        ids=[object_id],
        object_path=object_path,
        changes=changes,
        history_id=history_id,
        history_time=history_time)
    return True

def rename_children(request, parent, names):
    """ names is a list of 2-tuples (old_name, new_name) """
    if not names: return 0
    child_ids_and_names = []
    parent_id = parent._id
    parent_path = parent.resource_path()
    ids = [parent_id]
    renames = []
    for (old_name, new_name) in names:
        if old_name == new_name: continue
        obj = parent.get_child(old_name)
        if obj:
            child_id = obj._id
            ids.append(child_id)
            child_ids_and_names.append(dict(id=child_id, old_name=old_name, new_name=new_name))
            renames.append((old_name, new_name))
    count = parent.rename_children(renames)  # May raise a Veto
    log_history(request, 'rename',
        ids=ids,
        parent_id=parent_id,
        parent_path=parent_path,
        children=child_ids_and_names)
    return count

def rename_child(request, parent, old_name, new_name):
    return rename_children(request, parent, [(old_name, new_name)])

def rename_object(request, obj, new_name):
    return rename_child(request, obj.__parent__, obj.__name__, new_name)

def move_children(request, old_parent, new_parent, children):
    """ children is a list of child objects to be moved from old_parent to new_parent """
    if not children: return 0
    old_parent_id = old_parent._id
    old_parent_path = old_parent.resource_path()
    new_parent_id = new_parent._id
    new_parent_path = new_parent.resource_path()
    ids = [old_parent_id, new_parent_id]
    child_ids_and_names = []
    for obj in children:
        if obj.__parent__._id != old_parent_id:
            raise ValueError("move_children() called with inconsistent parameters; %s is not a direct child of %s." % (obj.resource_path(), old_parent_path))
        child_id = obj._id
        child_name = obj.__name__
        ids.append(child_id)
        child_ids_and_names.append(dict(id=child_id, name=child_name))
    new_parent.move_children(children)  # May raise a Veto
    log_history(request, 'move',
        ids=ids,
        old_parent_id=old_parent_id,
        old_parent_path=old_parent_path,
        new_parent_id=new_parent_id,
        new_parent_path=new_parent_path,
        children=child_ids_and_names)
    return len(children)

def move_object(request, obj, new_parent):
    return move_children(request, obj.__parent__, new_parent, [obj])


def copy_children(request, orig_parent, copy_parent, children):
    """ children is a list of child objects to be moved from orig_parent to copy_parent """
    if not children: return 0
    orig_parent_id = orig_parent._id
    orig_parent_path = orig_parent.resource_path()
    copy_parent_id = copy_parent._id
    copy_parent_path = copy_parent.resource_path()
    ids = [copy_parent_id] # Don't include the original parent in "ids"; it wasn't modified in any way.
    for obj in children:
        if obj.__parent__._id != orig_parent_id:
            raise ValueError("copy_children() called with inconsistent parameters; %s is not a direct child of %s." % (obj.resource_path(), orig_parent_path))

    child_ids_and_names = []
    for (orig_obj, copy_obj) in copy_parent.copy_children(children):  # May raise a Veto
        orig_id = orig_obj._id
        orig_name = orig_obj.__name__
        copy_id = copy_obj._id
        copy_name = copy_obj.__name__
        ids.append(copy_id)  # Don't include the original in "ids"; it wasn't modified in any way.
        child_ids_and_names.append(dict(orig_id=orig_id, orig_name=orig_name, id=copy_id, name=copy_name))
    log_history(request, 'copy',
        ids=ids,
        orig_parent_id=orig_parent_id,
        orig_parent_path=orig_parent_path,
        copy_parent_id=copy_parent_id,
        copy_parent_path=copy_parent_path,
        children=child_ids_and_names)
    return len(children)

def copy_object(request, obj, copy_parent):
    return copy_children(request, obj.__parent__, copy_parent, [obj])

def trash_children(request, parent, children):
    """ children is a list of child objects to be moved from parent to trash """
    if not children: return 0
    trash = parent.find_root()['trash']
    child_ids_and_names = []
    parent_id = parent._id
    parent_path = parent.resource_path()
    ids = [parent_id]
    for obj in children:
        child_id = obj._id
        child_name = obj.__name__
        ids.append(child_id)
        child_ids_and_names.append(dict(id=child_id, name=child_name))
        trash.move_child(obj)
    log_history(request, 'trash',
        ids=ids,
        parent_id=parent_id,
        parent_path=parent_path,
        children=child_ids_and_names)
    return len(children)

def trash_objects(request, objects):
    """ Trash the specified list of objects (which possibly have different parents). """
    if not objects: return 0
    root = objects[0].find_root()
    trash = root['trash']
    # The following code is complicated a bit by a desire to avoid deleting an object and one of its ancestors...
    # just deleting the ancestor is good enough.
    parents = [] # A list of 2 tuples (depth, object ID)
    children_by_parent_id = {}
    for obj in objects:
        parent = obj.__parent__
        parent_id = parent._id
        parents.append((len(parent.get_id_path()), parent._id))
        if not children_by_parent_id.has_key(parent_id):
            children_by_parent_id[parent_id] = []
        children_by_parent_id[parent_id].append(obj)
    # Sort parents by depth (shallow first) so that we delete objects closer to the root first.
    parents.sort()
    count = 0
    for parent_id in [x[1] for x in parents]:
        # Skip this parent if it's now in the trash...
        parent = root.get_content_by_id(parent_id)
        if parent and not parent.in_trash():
            children = children_by_parent_id[parent_id]
            count += trash_children(request, parent, children)
    return count

def trash_object(request, object):
    return trash_objects(request, [object])
        
def restore_objects(request, objects):
    if not objects: return 0
    root = objects[0].find_root()
    trash = root['trash']
    count = trash.restore_children(objects)  # May raise a Veto
    children_by_parent_id = {}
    for obj in objects:
        parent_id = obj.__parent__._id
        if not children_by_parent_id.has_key(parent_id):
            children_by_parent_id[parent_id] = []
        children_by_parent_id[parent_id].append(obj)
    for (parent_id, children) in children_by_parent_id.items():
        parent = root.get_content_by_id(parent_id)
        parent_path = parent.resource_path()
        ids = [parent_id]
        child_ids_and_names = []
        for obj in children:
            ids.append(obj._id)
            child_ids_and_names.append(dict(id=obj._id, name=obj.__name__))
        log_history(request, 'restore',
            ids=ids,
            parent_id=parent_id,
            parent_path=parent_path,
            children=child_ids_and_names)
    return count


def reorder_children(request, parent, child_names, target, delta=None):
    """ Target should be one of "top", "bottom", "up", "down".
    If target is "up" or "down", delta is a positive int that specifies the number of positions to move in
    that direction.
    """
    parent_id = parent._id
    parent_path = parent.resource_path()
    reordered_names = None
    if target == 'top':
        reordered_names = parent.reorder_names_to_top(child_names)
    elif target == 'bottom':
        reordered_names = parent.reorder_names_to_bottom(child_names)
    elif target == 'up':
        reordered_names = parent.reorder_names_up(child_names, delta)
    elif target == 'down':
        reordered_names = parent.reorder_names_down(child_names, delta)
    else:
        raise ValueError("Unexpected target value %s for reorder_children()" % repr(target)) 
    if reordered_names:
        log_history(request, 'reorder',
            ids=[parent_id],  # don't note child ids too; we consider this a folder-level operation
            parent_id=parent_id,
            parent_path=parent_path,
            child_names=reordered_names,
            target=target,
            delta=delta)
    return reordered_names
