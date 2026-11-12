from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

# ==============================================================================
# CUSTOM USER MANAGER
# = : Django needs a custom manager when we change the USERNAME_FIELD from
# = : the default 'username' to 'email'.
# ==============================================================================
class UserManager(BaseUserManager):
    """
    Handles creating and managing Users specifically using Email as the
    unique identifier instead of a username.
    """
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """Helper function to create and save a user with the given email and password."""
        if not email:
            raise ValueError("Email is required")

        # Normalize: convert to lower-case to ensure 'User@Example.com' is treated
        # the same as 'user@example.com'.
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password) # Hashes the password for security.
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """Creates a standard (non-admin) user."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        """Creates a superuser (admin) for the platform."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if not extra_fields.get("is_staff") or not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_staff and is_superuser enabled")

        return self._create_user(email, password, **extra_fields)


# ==============================================================================
# CUSTOM USER MODEL
# = : Extends Django's built-in 'AbstractUser'.
# ==============================================================================
class User(AbstractUser):
    """
    Our custom User model.
    By default, Django users have a 'username' field. We disable that and
    use 'email' as the primary login field.
    """
    username = None # Disable username field.
    email = models.EmailField(unique=True) # Ensure emails are unique across the app.

    # Tells Django to use the email field for authentication (logins).
    USERNAME_FIELD = "email"

    # REQUIRED_FIELDS are fields required when creating a user via 'createsuperuser'
    # (other than the USERNAME_FIELD and password).
    REQUIRED_FIELDS = []

    # Connects our custom manager to this model.
    objects = UserManager()

    def save(self, *args, **kwargs):
        """Ensures email is always clean (stripped and lowercase) before saving."""
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        """
        Returns full name if available, otherwise the email.
        This defines how the user appears in the Django Admin or as a ForeignKey.
        """
        return self.get_full_name() or self.email
