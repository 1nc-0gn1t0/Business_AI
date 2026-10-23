const labels: Record<string, string> = {
  relative_geographic_proxies_not_profitability:
    "Сравниваем географические признаки, а не прибыльность",
  straight_line_not_walking: "Расстояния по прямой, не пешие маршруты",
  saved_bbox_only: "Только в пределах загруженного покрытия",
  geographic_dispersion_not_ranking: "Кандидаты распределены географически",
  incomplete_or_insufficient_comparison:
    "Покрытие или данные недостаточны для полного сравнения",
  stale_osm_snapshot: "Набор OSM требует обновления",
  requested_region_clipped_to_coverage:
    "Область поиска ограничена фактическим покрытием",
  insufficient_observed_cells_or_separation:
    "Найдено меньше зон с учётом данных и заданного интервала",
  confirmed_profile_snapshot_required:
    "Требуется подтверждённый профиль бизнеса",
  profile_city_and_category_required: "Укажите город и тип бизнеса",
  profile_city_differs_from_dataset:
    "Город профиля не совпадает с набором геоданных",
  unsupported_business_category:
    "Для этого типа бизнеса ещё нет правил генерации зон",
  unmapped_profile_constraints:
    "Текстовые ограничения пока нельзя сопоставить с географическими правилами. Уточните профиль; они не будут проигнорированы",
  district_not_in_dataset: "Выбранного района нет в наборе данных",
  preferred_district_missing_or_ambiguous:
    "Район не найден или указан неоднозначно; проверьте название",
  district_constraints_disjoint: "Условия выбора районов не пересекаются",
  negative_operating_result: "Операционный результат отрицательный",
  positive_exact_margin_below_display_precision:
    "Положительная маржа меньше точности отображения",
  break_even_above_model_input_sales_limit:
    "Безубыточность за пределами допустимого числа продаж модели",
};
export const readable = (code: string) =>
  labels[code] ||
  "Есть дополнительные ограничения; подробности в методологии и исходных данных.";
