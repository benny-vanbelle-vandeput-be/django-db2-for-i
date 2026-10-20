from django.db import models


class Place(models.Model):
    name = models.CharField(max_length=20)


class Restaurant(Place):
    rating = models.IntegerField(default=0)
