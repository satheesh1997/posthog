from typing import Any, Dict, List, Optional, Tuple, Union

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models, transaction
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from .organization import Organization, OrganizationMembership
from .team import Team
from .utils import generate_random_token, sane_repr


class UserManager(BaseUserManager):
    """Define a model manager for User model with no username field."""

    use_in_migrations = True

    def create_user(self, email: str, password: Optional[str], first_name: str, **extra_fields) -> "User":
        """Create and save a User with the given email and password."""
        if email is None:
            raise ValueError("Email must be provided!")
        email = self.normalize_email(email)
        extra_fields.setdefault("distinct_id", generate_random_token())
        user = self.model(email=email, first_name=first_name, **extra_fields)
        if password is not None:
            user.set_password(password)
        user.save()
        return user

    def bootstrap(
        self,
        company_name: str,
        email: str,
        password: Optional[str],
        first_name: str = "",
        organization_fields: Optional[Dict[str, Any]] = None,
        team_fields: Optional[Dict[str, Any]] = None,
        **user_fields,
    ) -> Tuple["Organization", "Team", "User"]:
        """Instead of doing the legwork of creating a user from scratch, delegate the details with bootstrap."""
        with transaction.atomic():
            organization_fields = organization_fields or {}
            organization_fields.setdefault("name", company_name)
            organization = Organization.objects.create(**organization_fields)
            user = self.create_user(email=email, password=password, first_name=first_name, **user_fields)
            team = Team.objects.create_with_data(user=user, organization=organization, **(team_fields or {}))
            user.join(
                organization=organization, level=OrganizationMembership.Level.ADMIN,
            )
            return organization, team, user

    def create_and_join(
        self,
        organization: Organization,
        email: str,
        password: Optional[str],
        first_name: str = "",
        level: OrganizationMembership.Level = OrganizationMembership.Level.MEMBER,
        **extra_fields,
    ) -> "User":
        with transaction.atomic():
            user = self.create_user(email=email, password=password, first_name=first_name, **extra_fields)
            membership = user.join(organization=organization, level=level)
            return user


class User(AbstractUser):
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: List[str] = []

    DISABLED = "disabled"
    TOOLBAR = "toolbar"
    TOOLBAR_CHOICES = [
        (DISABLED, DISABLED),
        (TOOLBAR, TOOLBAR),
    ]

    username = None  # type: ignore
    current_organization = models.ForeignKey(
        "posthog.Organization", models.SET_NULL, null=True, related_name="users_currently+",
    )
    current_team = models.ForeignKey("posthog.Team", models.SET_NULL, null=True, related_name="teams_currently+")
    email = models.EmailField(_("email address"), unique=True)
    temporary_token: models.CharField = models.CharField(max_length=200, null=True, blank=True, unique=True)
    distinct_id: models.CharField = models.CharField(max_length=200, null=True, blank=True, unique=True)
    email_opt_in: models.BooleanField = models.BooleanField(default=False, null=True, blank=True)
    anonymize_data: models.BooleanField = models.BooleanField(default=False, null=True, blank=True)
    toolbar_mode: models.CharField = models.CharField(
        max_length=200, null=True, blank=True, choices=TOOLBAR_CHOICES, default=TOOLBAR
    )

    objects: UserManager = UserManager()  # type: ignore

    @property
    def ee_available(self) -> bool:
        return settings.EE_AVAILABLE

    @property
    def is_superuser(self) -> bool:  # type: ignore
        return self.is_staff

    @property
    def teams(self):
        return Team.objects.filter(organization__in=self.organizations.all())

    @property
    def organization(self) -> Organization:
        if self.current_organization is None:
            self.current_organization = self.organizations.first()
            assert self.current_organization is not None, "Null current organization is not supported yet!"
            self.save()
        return self.current_organization

    @property
    def team(self) -> Team:
        if self.current_team is None:
            self.current_team = self.organization.teams.first()
            assert self.current_team is not None, "Null current team is not supported yet!"
            self.save()
        return self.current_team

    def join(
        self, *, organization: Organization, level: OrganizationMembership.Level = OrganizationMembership.Level.MEMBER,
    ) -> OrganizationMembership:
        with transaction.atomic():
            membership = OrganizationMembership.objects.create(user=self, organization=organization, level=level)
            self.current_organization = organization
            self.current_team = organization.teams.first()
            self.save()
            return membership

    def leave(self, *, organization: Organization) -> None:
        with transaction.atomic():
            OrganizationMembership.objects.get(user=self, organization=organization).delete()
            if self.organizations.exists():
                self.delete()
            else:
                if self.current_organization == organization:
                    self.current_organization = self.organizations.first()
                if self.current_organization is not None:
                    self.current_team = self.current_organization.teams.first()
                self.save()

    __repr__ = sane_repr("email", "first_name", "distinct_id")
