# Pigeon calls these Kotlin suspend methods by reflection. R8 was removing
# SharedPreferencesApiRegistrar.getAll, which crashed Supabase on the phone.
-keep class io.flutter.plugins.sharedpreferences.** { *; }
-keepclassmembers class io.flutter.plugins.sharedpreferences.** { *; }
