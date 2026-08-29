from uuid import uuid4

from django.db import models
from django.utils.text import slugify


class Pod(models.Model):
    name = models.CharField(max_length=100, help_text="Nome do playgroup")
    slug = models.SlugField(unique=True, blank=True)
    invite_token = models.UUIDField(
        default=uuid4,
        unique=True,
        help_text="Usado para montar o link de convite; regenerar invalida o link anterior",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        base_slug = slugify(self.name)
        slug = base_slug
        suffix = 1
        while Pod.objects.filter(slug=slug).exists():
            suffix += 1
            slug = f"{base_slug}-{suffix}"
        return slug

    def regenerate_invite_token(self):
        self.invite_token = uuid4()
        self.save(update_fields=["invite_token"])

    def __str__(self):
        return self.name
