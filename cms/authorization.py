from zope.interface import implements
from pyramid.interfaces import IAuthorizationPolicy
from pyramid.authorization import ACLAuthorizationPolicy

import logging
log = logging.getLogger(__name__)

class ACLAuthorizationPolicyWithLocalRoles(object):
    # FIXME: document this
    # Basically it uses the standard Pyramid ACLAuthorizationPolicy 
    # and adds support for our local roles.
    implements(IAuthorizationPolicy)

    def __init__(self):
        self.acl_policy = ACLAuthorizationPolicy()

    def permits(self, context, principals, permission):
        #log.debug("permits(context=%s, principals=%s, permission=%s)" % (repr(context), repr(principals), repr(permission)))
        try:
            local_roles = context._get_merged_local_roles()
        except AttributeError:
            local_roles = None
        if local_roles:
            expanded_principals = set(principals)
            for p in principals:
                roles = local_roles.get(p)
                if roles:
                    expanded_principals.update(roles)
            #log.debug("in permits - local_roles=%s expanded_principals=%s" % (repr(local_roles), repr(expanded_principals)))
            principals = expanded_principals
        return self.acl_policy.permits(context, principals, permission)

    def principals_allowed_by_permission(self, context, permission):
        #log.debug("principals_allowed_by_permission(context=%s, permission=%s)" % (repr(context), repr(permission)))
        allowed = self.acl_policy.principals_allowed_by_permission(context, permission)
        try:
            local_roles = context._get_merged_local_roles()
        except AttributeError:
            local_roles = None
        if local_roles:
            principals_by_role = _invert_local_roles(local_roles)
            expanded_allowed = set(allowed)
            for r in allowed:
                principals = principals_by_role.get(r)
                if principals:
                    expanded_allowed.update(principals)
            #log.debug("in principals_allowed_by_permission - local_roles=%s allowed=%s expanded_allowed=%s" % (repr(local_roles), repr(allowed), repr(expanded_allowed)))
            allowed = expanded_allowed
        return allowed

def _invert_local_roles(local_roles):
    # Given a dictionary where each key is a principal name and each value is a sequence of "role" principals,
    # return a dictionary where each key is a role prinicipal and each value is a set of principal names.
    result = {}
    for (principal, roles) in local_roles.items():
        for role in roles:
            s = result.get(role, set())
            s.add(principal)
            result[role] = s
    return result
