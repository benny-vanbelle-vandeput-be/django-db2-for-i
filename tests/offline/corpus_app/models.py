from django.db import models


class Place(models.Model):
    name = models.CharField(max_length=20)


class Restaurant(Place):
    rating = models.IntegerField(default=0)


class Dish(models.Model):
    """An M2M with an auto-created through model (Dish_places), which plain pickle
    cannot store by reference."""

    name = models.CharField(max_length=20)
    places = models.ManyToManyField(Place)
