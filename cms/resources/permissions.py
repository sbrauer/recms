from pyramid.security import Allow, Deny, Everyone, Authenticated, ALL_PERMISSIONS, principals_allowed_by_permission, effective_principals, has_permission
#
# Our default workflow assumes a small team maintaining the content of a website.
# There are 3 workflow states (private, pending, and public) and 3 user groups (superuser, publisher
# and submitter).
#
# Anonymous users can view the site itself and any of its children in the public state, and any of their
# public children, etc.  Any node in the object tree that is in a non-published state denies anonymous
# VIEW permission for itself and all of its children recursively.
#
# Authenticated users can view everything regardless of state.
#
# Members of the submitter group can add new content, but can't publish it.
# They can only submit it for review by a member of the publisher group
# (transitioning it into the pending state).
# Submitter members can only edit private content.
# They must retract pending content back into the private state in order to edit it.
#
# Members of the publisher group can publish content and can edit all content regardless of state.
# However they cannot manage users or groups.
#
# Members of the superuser group can do anything that the system allows.

#################################################
# Define permissions
#################################################
VIEW = 'view' # can view context
EDIT = 'edit' # can edit/rename/delete context
ADD = 'add' # can add child objects
PUBLISH = 'publish' # can perform workflow transitions that move context into or out of the 'published' state
SUBMIT = 'submit' # can perform workflow transitions that move context into or out of the 'pending' state
SET_ROLES = 'set_roles' # can set local roles


#################################################
# Default acl policies
#################################################
# FIXME: need an easy way for sites to override these...

# For Users, Groups, and other special access (tbd).
superuser_only_acl= [
    (Allow, 'group:superuser', ALL_PERMISSIONS),
    (Deny, Everyone, ALL_PERMISSIONS),
]

# For the Root itself
root_acl= [
    (Allow, 'group:superuser', ALL_PERMISSIONS),
    (Allow, 'group:publisher', (EDIT, ADD, PUBLISH, SUBMIT)),
    (Allow, 'group:submitter', (ADD, SUBMIT)),
    (Allow, Everyone, VIEW),
    (Deny, Everyone, ALL_PERMISSIONS),
]

# acl for each workflow state
acl_by_state = dict(
    private = [
        (Allow, Authenticated, VIEW),
        (Allow, 'group:submitter', EDIT),
        (Deny, Everyone, VIEW),
    ],
    pending = [
        (Allow, Authenticated, VIEW),
        (Deny, 'group:submitter', ADD),  # Not 100% sure this is the best default policy.
        (Deny, Everyone, VIEW),
    ],
    public = [
        (Allow, Authenticated, VIEW),
        # We purposefully don't Allow Everyone VIEW.
        # We want Everyone to inherit VIEW permission so that non-published folders and all of their
        # contents are inaccessible to anonymous users.
    ],
)

# Special acl for the trash collection and everything in it.
trash_acl= [
    (Allow, Authenticated, VIEW),
    (Deny, Everyone, ALL_PERMISSIONS),
]
