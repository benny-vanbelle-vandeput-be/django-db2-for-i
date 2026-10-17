"""Models used by the offline and pub400 tiers."""

import uuid

from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=100)


class Book(models.Model):
    id = models.BigAutoField(primary_key=True)
    author = models.ForeignKey(Author, models.CASCADE)
    title = models.CharField(max_length=200, db_index=True)
    published = models.DateTimeField(null=True)
    reading_time = models.TimeField(null=True)
    available = models.BooleanField(default=True)
    pages = models.PositiveIntegerField(default=0)


class Node(models.Model):
    id = models.SmallAutoField(primary_key=True)
    parent = models.ForeignKey("self", models.CASCADE, null=True)


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    label = models.SlugField(unique=True)
