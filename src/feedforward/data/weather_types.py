"""Weather types (the dropdown of the admin form and the what if) and the rain level each one means."""

# Weather type (the admin dropdown) to rain level, from how the dataset maps condition text.
WEATHER_TYPE_RAIN_LEVEL = {
    "Mist": 0, "Haze": 0, "Fair": 0, "Partly Cloudy": 0, "Fog": 0, "Smoke": 0, "Dry": 0,
    "Showers in the Vicinity": 1, "Drizzle": 1, "Light Drizzle": 1, "Light Rain": 1,
    "Rain": 2, "Thunder": 2, "Light Rain with Thunder": 2, "Heavy Rain": 3,
}
