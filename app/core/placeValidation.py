import re
from typing import Any


dayNames = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

supplyAvailabilityValues = {
    "available",
    "subject-to-availability",
    "limited",
    "seasonal",
}

placeFields = {
    "id",
    "name",
    "type",
    "description",
    "needsReferral",
    "supplies",
    "placeId",
    "address",
    "coord",
    "openingHours",
}

requiredPlaceFields = {
    "name",
    "type",
    "needsReferral",
    "supplies",
    "coord",
    "openingHours",
}

supplyFields = {
    "name",
    "description",
    "availability",
    "inStock",
    "needsReferral",
    "notes",
}

coordinateFields = {"latitude", "longitude"}
openingPeriodFields = {"open", "close"}
optionalPlaceTextFields = ("description", "placeId", "address")
timePattern = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
minimumLatitude = -90.0
maximumLatitude = 90.0
minimumLongitude = -180.0
maximumLongitude = 180.0


class PlaceValidationError(ValueError):
    pass


def requireObject(value: Any, fieldName: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlaceValidationError(f"{fieldName} must be an object")
    return value


def requireString(value: Any, fieldName: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlaceValidationError(f"{fieldName} must be a non-empty string")
    return value.strip()


def optionalString(value: Any, fieldName: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PlaceValidationError(f"{fieldName} must be a string or null")
    trimmedValue = value.strip()
    return trimmedValue or None


def requireBool(value: Any, fieldName: str) -> bool:
    if not isinstance(value, bool):
        raise PlaceValidationError(f"{fieldName} must be a boolean")
    return value


def requireNumber(value: Any, fieldName: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlaceValidationError(f"{fieldName} must be a number")
    return float(value)


def validateTypes(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise PlaceValidationError("type must be a non-empty array")

    validatedTypes: list[str] = []
    seenTypes: set[str] = set()

    for index, typeValue in enumerate(value):
        validatedType = requireString(typeValue, f"type[{index}]")
        normalizedType = validatedType.lower()
        if normalizedType not in seenTypes:
            seenTypes.add(normalizedType)
            validatedTypes.append(validatedType)

    if not validatedTypes:
        raise PlaceValidationError("type must contain at least one value")

    return validatedTypes


def validateSupply(value: Any, index: int) -> dict[str, Any]:
    supply = requireObject(value, f"supplies[{index}]")
    unknownFields = set(supply) - supplyFields
    if unknownFields:
        raise PlaceValidationError(
            f"supplies[{index}] has unknown fields: {', '.join(sorted(unknownFields))}"
        )

    availability = supply.get("availability")
    if availability not in supplyAvailabilityValues:
        allowedValues = ", ".join(sorted(supplyAvailabilityValues))
        raise PlaceValidationError(
            f"supplies[{index}].availability must be one of: {allowedValues}"
        )

    validatedSupply = {
        "name": requireString(supply.get("name"), f"supplies[{index}].name"),
        "availability": availability,
        "inStock": requireBool(supply.get("inStock"), f"supplies[{index}].inStock"),
        "needsReferral": requireBool(
            supply.get("needsReferral"), f"supplies[{index}].needsReferral"
        ),
    }

    description = optionalString(
        supply.get("description"), f"supplies[{index}].description"
    )
    notes = optionalString(supply.get("notes"), f"supplies[{index}].notes")

    if description is not None:
        validatedSupply["description"] = description
    if notes is not None:
        validatedSupply["notes"] = notes

    return validatedSupply


def validateSupplies(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise PlaceValidationError("supplies must be an array")
    return [validateSupply(supplyValue, index) for index, supplyValue in enumerate(value)]


def validateCoord(value: Any) -> dict[str, float]:
    coord = requireObject(value, "coord")
    if set(coord) != coordinateFields:
        raise PlaceValidationError("coord must contain only latitude and longitude")

    latitude = requireNumber(coord.get("latitude"), "coord.latitude")
    longitude = requireNumber(coord.get("longitude"), "coord.longitude")

    if not minimumLatitude <= latitude <= maximumLatitude:
        raise PlaceValidationError("coord.latitude must be between -90 and 90")
    if not minimumLongitude <= longitude <= maximumLongitude:
        raise PlaceValidationError("coord.longitude must be between -180 and 180")

    return {"latitude": latitude, "longitude": longitude}


def validateOpeningHours(value: Any) -> dict[str, list[dict[str, str]]]:
    openingHours = requireObject(value, "openingHours")
    if set(openingHours) != set(dayNames):
        raise PlaceValidationError("openingHours must contain all seven days")

    validatedOpeningHours: dict[str, list[dict[str, str]]] = {}

    for dayName in dayNames:
        periods = openingHours.get(dayName)
        if not isinstance(periods, list):
            raise PlaceValidationError(f"openingHours.{dayName} must be an array")

        validatedOpeningHours[dayName] = []
        for index, periodValue in enumerate(periods):
            period = requireObject(periodValue, f"openingHours.{dayName}[{index}]")
            if set(period) != openingPeriodFields:
                raise PlaceValidationError(
                    f"openingHours.{dayName}[{index}] must contain only open and close"
                )

            openTime = requireString(
                period.get("open"), f"openingHours.{dayName}[{index}].open"
            )
            closeTime = requireString(
                period.get("close"), f"openingHours.{dayName}[{index}].close"
            )

            if not timePattern.fullmatch(openTime):
                raise PlaceValidationError(
                    f"openingHours.{dayName}[{index}].open must use HH:MM"
                )
            if not timePattern.fullmatch(closeTime):
                raise PlaceValidationError(
                    f"openingHours.{dayName}[{index}].close must use HH:MM"
                )

            validatedOpeningHours[dayName].append({"open": openTime, "close": closeTime})

    return validatedOpeningHours


def validatePlace(value: Any, allowId: bool = True) -> dict[str, Any]:
    place = requireObject(value, "place")
    allowedFields = placeFields if allowId else placeFields - {"id"}
    unknownFields = set(place) - allowedFields
    if unknownFields:
        raise PlaceValidationError(
            f"Unknown place fields: {', '.join(sorted(unknownFields))}"
        )

    missingFields = requiredPlaceFields - set(place)
    if missingFields:
        raise PlaceValidationError(
            f"Missing place fields: {', '.join(sorted(missingFields))}"
        )

    validatedPlace: dict[str, Any] = {
        "name": requireString(place.get("name"), "name"),
        "type": validateTypes(place.get("type")),
        "needsReferral": requireBool(place.get("needsReferral"), "needsReferral"),
        "supplies": validateSupplies(place.get("supplies")),
        "coord": validateCoord(place.get("coord")),
        "openingHours": validateOpeningHours(place.get("openingHours")),
    }

    if allowId and "id" in place:
        validatedPlace["id"] = requireString(place.get("id"), "id")

    for fieldName in optionalPlaceTextFields:
        textValue = optionalString(place.get(fieldName), fieldName)
        if textValue is not None:
            validatedPlace[fieldName] = textValue

    return validatedPlace
