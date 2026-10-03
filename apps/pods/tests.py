from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.pods.models import Membership, Pod


class PodAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.pod = Pod.objects.create(name="Pod de Teste")
        self.member = User.objects.create_user("membro", password="x")
        self.outsider = User.objects.create_user("fora", password="x")
        Membership.objects.create(pod=self.pod, user=self.member)
        self.url = reverse("core:dashboard", kwargs={"pod_slug": self.pod.slug})

    def test_anonymous_is_redirected_to_login_with_next(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response,
            f"/accounts/login/?next={self.url}",
            fetch_redirect_response=False,
        )

    def test_anonymous_is_redirected_on_owner_only_view(self):
        url = reverse("pod:pod-settings", kwargs={"pod_slug": self.pod.slug})
        response = self.client.get(url)
        self.assertRedirects(
            response, f"/accounts/login/?next={url}", fetch_redirect_response=False
        )

    def test_non_member_gets_404(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_member_can_access(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_unknown_pod_slug_gets_404_when_logged_in(self):
        self.client.force_login(self.member)
        url = reverse("core:dashboard", kwargs={"pod_slug": "nao-existe"})
        self.assertEqual(self.client.get(url).status_code, 404)
