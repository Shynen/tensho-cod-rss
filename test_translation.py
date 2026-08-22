import argostranslate.package
import argostranslate.translate

print("Mise à jour des modèles Argos...")

argostranslate.package.update_package_index()

packages = argostranslate.package.get_available_packages()

package = next(
    p for p in packages
    if p.from_code == "en" and p.to_code == "fr"
)

print("Téléchargement du modèle EN → FR...")

argostranslate.package.install_from_path(
    package.download()
)

print("Traduction...")

result = argostranslate.translate.translate(
    "Modern Warfare 4 Open Beta: Everything You Need to Know",
    "en",
    "fr"
)

print("Résultat :")
print(result)
