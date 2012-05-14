def reorder_ids_by_delta(all_ids, ids_to_reorder, delta):
    """ Given a list of ID strings, another list that should be a subset of
    those ID strings, and a signed int delta value, reorder the items in
    the all_ids list such that the specified subset of IDs are moved by the
    delta value.
    A negative delta moves items closer to the beginning (index 0) of the list.
    A positive delta moves items closer to the end of the list.
    """
    reordered_ids = []
    # Logic borrowed from Zope/lib/python/OFS/OrderSupport.py
    min_position = 0
    # unify moving direction
    if delta > 0:
        ids_to_reorder.reverse()
        all_ids.reverse()

    for id in ids_to_reorder:
        if id in all_ids:
            old_position = all_ids.index(id)
            new_position = max(old_position - abs(delta), min_position)
            if new_position == min_position:
                min_position += 1
            if old_position != new_position:
                all_ids.remove(id)
                all_ids.insert(new_position, id)
                reordered_ids.append(id)

    if delta > 0: all_ids.reverse()
    return reordered_ids

def reorder_ids_up(all_ids, ids_to_reorder, delta=1):
    return reorder_ids_by_delta(all_ids, ids_to_reorder, -delta)

def reorder_ids_down(all_ids, ids_to_reorder, delta=1):
    return reorder_ids_by_delta(all_ids, ids_to_reorder, delta)

def reorder_ids_to_top(all_ids, ids_to_reorder):
    reordered_ids = []
    # Figure out which ones will actually move...
    idx = 0
    for id in ids_to_reorder:
        if all_ids[idx] != id:
            reordered_ids.append(id)
        idx += 1
    if not reordered_ids: return reordered_ids

    ids_to_reorder.reverse()
    for id in ids_to_reorder:
        if id in all_ids:
            all_ids.remove(id)
            all_ids.insert(0, id)
    return reordered_ids

def reorder_ids_to_bottom(all_ids, ids_to_reorder):
    reordered_ids = []
    # Figure out which ones will actually move...
    idx = -len(ids_to_reorder)
    for id in ids_to_reorder:
        if all_ids[idx] != id:
            reordered_ids.append(id)
        idx += 1
    if not reordered_ids: return reordered_ids

    for id in ids_to_reorder:
        if id in all_ids:
            all_ids.remove(id)
            all_ids.append(id)
    return reordered_ids
