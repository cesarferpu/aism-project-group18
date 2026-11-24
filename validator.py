def validate_players(criteria, candidates):
    """Independently enforce every mandatory constraint from the extracted profile."""
    valid = []
    for player in candidates:
        try:
            age = float(player["age"])
            age_limit = criteria.get("max_age")
            age_ok = True if age_limit is None else (
                age < float(age_limit) if criteria.get("age_limit_exclusive", False)
                else age <= float(age_limit)
            )
            value_limit = criteria.get("max_value_m")
            value_ok = True if value_limit is None else (
                float(player["value_m"]) < float(value_limit) if criteria.get("value_limit_exclusive", False)
                else float(player["value_m"]) <= float(value_limit)
            )
            checks = [
                criteria.get("position") in (None, "", "Any", "Cualquiera", player.get("position")),
                criteria.get("nationality") in (None, "", "Any", "Cualquiera", player.get("nationality")),
                criteria.get("club") in (None, "", "Any", "Cualquiera", player.get("club")),
                criteria.get("league") in (None, "", "Any", "Cualquiera", player.get("league")),
                age_ok,
                criteria.get("min_goals") is None or float(player["goals"]) >= float(criteria["min_goals"]),
                criteria.get("min_assists") is None or float(player["assists"]) >= float(criteria["min_assists"]),
                criteria.get("min_appearances") is None or float(player["appearances"]) >= float(criteria["min_appearances"]),
                criteria.get("min_minutes") is None or float(player["minutes"]) >= float(criteria["min_minutes"]),
                value_ok,
                criteria.get("max_height_cm") is None or float(player["height_cm"]) <= float(criteria["max_height_cm"]),
            ]
        except (KeyError, TypeError, ValueError):
            checks = [False]
        if all(checks):
            valid.append(player)
    return valid
