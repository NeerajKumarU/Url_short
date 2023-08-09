from django.urls import path
from . import views


urlpatterns = [
  path('',views.home),
  path('shorturl',views.makeShortUrl),
  path('<str:shorturl>',views.redirecturl)
]

