# dam2stix
Code voor Rijnland conversie DAM invoer naar STIX bestanden

## Werkwijze

* Clone het script met ```git clone git@github.com:breinbaas/dam2stix.git``` of download als ZIP en pak uit 
* Ga naar deze map (de locatie waar ```main.py``` staat)
* Maak een map ```data/input``` en ```data/output``` in deze directory aan (**LET OP** als je de code cloned worden deze mappen vanzelf aangemaakt)
* Open een console in deze map
* Creeer een virtuele omgeving ```python -m venv .venv```
* Activeer de virtuele omgeving ```.venv\Scripts\activate``` (let op dat je autocompletion kunt gebruiken met TAB)
* Installeer de afhankelijkheden ```python -m pip install -r requirements.txt```
* Plaats de benodigde csv bestanden in de data/input directory
* Voer de code uit ```python main.py```

De gegenereerde bestanden komen in de ```data/output``` directory en bestaan uit .log bestanden met de gebruikte invoergegevens en de .stix bestanden met de berekeningen.

## Benodigde invoerbestanden

* combinationfile.csv
* slopelayers.csv
* soilprofiles.csv
* characteristicpoints.csv
* combinationfile.csv
* soilparameters.csv

Alle bestanden m.u.v. ```soilparameters.csv``` komen uit de DAM invoer bestanden. Een voorbeeld van het ```soilparameters.csv``` bestand is hieronder weergegeven;

```
code;yd;ys;phi;cohesie
Veen > 300;10.3;10.3;20.0;2.0
Veen < 300;11.4;11.4;20.0;2.0
Klei humeus <14;13.3;13.3;25.5;1.4
Klei siltig 14,5-16,5;15.4;15.4;26.8;2.8
Klei zandig >16,5;17.7;17.7;30.8;1.5
Zand;18;20;32.5;0.0
Zand_WL;18;20;32.5;0.0
Basisveen;12;12;20;2
Pleistoceen zand;18;20;32.5;0
ophoogmateriaal_klei;17;17;16.9;1.5
```

**LET OP** als je de code cloned wordt dit bestand automatisch aangemaakt.

In de output directory wordt het bestand ```areas.csv``` aangemaakt met daarin de oppervlaktes per grondsoort per berekening. Let op dat de veldscheiding in dit csv bestand de **puntkomma** en de decimaalscheiding een **punt** is.

## TODO

* code Zand_WL komt af en toe voor, parameters? Voor nu opgelost door dezelfde parameters als voor Zand te gebruiken
* let op dat grondsoort codes case sensitive zijn (vooralsnog geen fouten hierdoor)
* Dit werkt nu met x,z coordinaten, **als er DAM invoer is met x,y,z coordinaten dan werkt dit nog niet!**
