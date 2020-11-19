from typing import cast

from django.db.models import Model, QuerySet, query
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, mixins, response, serializers, status, viewsets
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.serializers import raise_errors_on_nested_writes
from rest_framework_extensions.mixins import NestedViewSetMixin

from posthog.models import OrganizationMembership
from posthog.permissions import OrganizationMemberPermissions, extract_organization


class OrganizationMemberObjectPermissions(BasePermission):
    """Require organization admin level to change object, allowing everyone read AND delete."""

    message = "Your cannot edit other organization members or remove anyone but yourself."

    def has_object_permission(self, request: Request, view, object: OrganizationMembership) -> bool:
        if request.method in SAFE_METHODS:
            return True
        if request.method == "DELETE" and object.user_id == request.user.id:
            return True
        organization = extract_organization(object)
        return (
            OrganizationMembership.objects.get(user_id=request.user.id, organization=organization).level
            >= OrganizationMembership.Level.ADMIN
        )


class OrganizationMemberSerializer(serializers.ModelSerializer):
    user_first_name = serializers.CharField(source="user.first_name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    membership_id = serializers.CharField(source="id", read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = ["membership_id", "user_id", "user_first_name", "user_email", "level", "joined_at", "updated_at"]

    def update(self, updated_membership, validated_data):
        updated_membership = cast(OrganizationMembership, updated_membership)
        raise_errors_on_nested_writes("update", self, validated_data)
        requesting_membership: OrganizationMembership = OrganizationMembership.objects.get(
            organization=updated_membership.organization, user=self.context["request"].user
        )
        new_level = validated_data.get("level")
        with transaction.atomic():
            if new_level is not None:
                # level changing constraints
                if updated_membership.id == requesting_membership.id:
                    raise exceptions.PermissionDenied("You can't change your own access level.")
                if updated_membership.level >= requesting_membership.level:
                    raise exceptions.PermissionDenied(
                        "You can only change access level of others with level lower than you."
                    )
                if new_level == OrganizationMembership.Level.OWNER:
                    if requesting_membership.level != OrganizationMembership.Level.OWNER:
                        raise exceptions.PermissionDenied(
                            "You can only pass on organization ownership if you're its owner."
                        )
                    requesting_membership.level = OrganizationMembership.Level.ADMIN
                    requesting_membership.save()
                elif new_level >= requesting_membership.level:
                    raise exceptions.PermissionDenied(
                        "You can only change access level of others to lower than your current one."
                    )
            for attr, value in validated_data.items():
                setattr(updated_membership, attr, value)
            updated_membership.save()
        return updated_membership


class OrganizationMemberViewSet(
    NestedViewSetMixin,
    mixins.DestroyModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OrganizationMemberSerializer
    permission_classes = [IsAuthenticated, OrganizationMemberPermissions, OrganizationMemberObjectPermissions]
    queryset = OrganizationMembership.objects.all()
    lookup_field = "user_id"
    ordering = ["level", "-joined_at"]

    def filter_queryset_by_parents_lookups(self, queryset) -> QuerySet:
        parents_query_dict = self.get_parents_query_dict()
        if parents_query_dict:
            if parents_query_dict["organization_id"] == "@current":
                parents_query_dict["organization_id"] = self.request.user.organization.id
            try:
                return queryset.filter(**parents_query_dict)
            except ValueError:
                raise exceptions.NotFound()
        else:
            return queryset

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_value = self.kwargs[self.lookup_field]
        if lookup_value == "@me":
            return queryset.get(user=self.request.user)
        filter_kwargs = {self.lookup_field: lookup_value}
        obj = get_object_or_404(queryset, **filter_kwargs)
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_destroy(self, instance: Model):
        instance = cast(OrganizationMembership, instance)
        instance.user.leave(organization=instance.organization)
