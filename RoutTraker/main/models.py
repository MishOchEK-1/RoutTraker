from django.conf import settings
from django.db import models


class Cabinet(models.Model):
    name = models.CharField("Кабинет", max_length=32, unique=True)
    sort_order = models.PositiveIntegerField("Порядок", default=0)
    can_be_skipped = models.BooleanField("Можно пропустить", default=False)
    included = models.BooleanField("Участвует в проверке", default=True)
    availability_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cabinet_availability_updates",
        verbose_name="Кто менял участие",
    )
    availability_updated_at = models.DateTimeField(
        "Когда меняли участие",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name = "Кабинет"
        verbose_name_plural = "Кабинеты"

    def __str__(self) -> str:
        return self.name


class ChecklistItem(models.Model):
    title = models.CharField("Пункт чеклиста", max_length=255)
    sort_order = models.PositiveIntegerField("Порядок", default=0)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Пункт чеклиста"
        verbose_name_plural = "Пункты чеклиста"

    def __str__(self) -> str:
        return self.title


class ChecklistResult(models.Model):
    class Status(models.TextChoices):
        UNCHECKED = "unchecked", "Не проверено"
        DONE = "done", "Выполнено"
        PROBLEM = "problem", "Проблема"

    cabinet = models.ForeignKey(
        Cabinet,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name="Кабинет",
    )
    item = models.ForeignKey(
        ChecklistItem,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name="Пункт чеклиста",
    )
    status = models.CharField(
        "Статус",
        max_length=16,
        choices=Status.choices,
        default=Status.UNCHECKED,
    )
    comment = models.TextField("Комментарий", blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_updates",
        verbose_name="Кто обновил",
    )
    updated_at = models.DateTimeField("Когда обновили", null=True, blank=True)

    class Meta:
        ordering = ("cabinet__sort_order", "item__sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("cabinet", "item"),
                name="unique_checklist_result",
            )
        ]
        verbose_name = "Результат проверки"
        verbose_name_plural = "Результаты проверки"

    def __str__(self) -> str:
        return f"{self.cabinet} / {self.item}"


class ActivityLog(models.Model):
    class Action(models.TextChoices):
        RESULT_UPDATED = "result_updated", "Обновление пункта"
        CABINET_TOGGLED = "cabinet_toggled", "Изменение участия кабинета"
        ALL_RESET = "all_reset", "Сброс чеклиста"
        ITEM_CREATED = "item_created", "Создание пункта"
        ITEM_DELETED = "item_deleted", "Удаление пункта"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
        verbose_name="Пользователь",
    )
    action = models.CharField("Действие", max_length=32, choices=Action.choices)
    cabinet_name = models.CharField("Кабинет", max_length=32, blank=True)
    item_title = models.CharField("Пункт", max_length=255, blank=True)
    status = models.CharField("Статус", max_length=16, blank=True)
    comment = models.TextField("Комментарий", blank=True)
    details = models.CharField("Детали", max_length=255, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "Журнал действий"
        verbose_name_plural = "Журнал действий"

    def __str__(self) -> str:
        return f"{self.get_action_display()} ({self.created_at:%d.%m %H:%M})"


class InspectionState(models.Model):
    round_number = models.PositiveIntegerField("Номер обхода", default=1)
    last_reset_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inspection_resets",
        verbose_name="Кто запустил обход",
    )
    last_reset_at = models.DateTimeField(
        "Когда начат обход",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Текущий обход"
        verbose_name_plural = "Текущий обход"

    def __str__(self) -> str:
        return f"Обход #{self.round_number}"


class CabinetCheck(models.Model):
    class Status(models.TextChoices):
        UNCHECKED = "unchecked", "Не проверено"
        DONE = "done", "Выполнено"
        PROBLEM = "problem", "Проблема"

    cabinet = models.OneToOneField(
        Cabinet,
        on_delete=models.CASCADE,
        related_name="current_check",
        verbose_name="Кабинет",
    )
    status = models.CharField(
        "Статус",
        max_length=16,
        choices=Status.choices,
        default=Status.UNCHECKED,
    )
    comment = models.TextField("Комментарий", blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cabinet_check_updates",
        verbose_name="Кто обновил",
    )
    updated_at = models.DateTimeField("Когда обновили", null=True, blank=True)

    class Meta:
        ordering = ("cabinet__sort_order", "cabinet__name")
        verbose_name = "Статус кабинета"
        verbose_name_plural = "Статусы кабинетов"

    def __str__(self) -> str:
        return f"{self.cabinet} / {self.get_status_display()}"
