from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r'vkeys', VKeyView, basename="vkeys")
router.register(r'elements', ElementView, basename="elements")
router.register(r'', VDocsView, basename="vdocs")

urlpatterns = [
  path('', include(router.urls)),
  path("undo-redo", UndoRedo.as_view(), name="undo-redo")
]
