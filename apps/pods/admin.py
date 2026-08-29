from django.contrib import admin
from .models import Membership, Pod


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0


@admin.register(Pod)
class PodAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MembershipInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "pod", "role", "created_at")
    list_filter = ("role", "pod")
    search_fields = ("user__username", "user__email", "pod__name")
