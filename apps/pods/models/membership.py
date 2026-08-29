from django.conf import settings
from django.db import models

from .pod import Pod


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Dono"
        MEMBER = "member", "Membro"

    pod = models.ForeignKey(Pod, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("pod", "user")
        ordering = ["created_at"]

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    def __str__(self):
        return f"{self.user} em {self.pod} ({self.get_role_display()})"
