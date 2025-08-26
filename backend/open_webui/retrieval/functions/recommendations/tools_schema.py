tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "get_recommendation",
            "description": """
                Fetches a list of most relevant recommendation for given tags.
                
                Tag list: 
                - Allergien
                - Alterung
                - Angstzustände, Angst
                - Anspannung
                - Antibiotikatherapie
                - Antriebslosigkeit
                - Appetitlosigkeit
                - Arteriosklerose
                - Arthritis
                - Arthrose
                - Asthma
                - Augenprobleme, Sehschwäche, Rötung
                - Autoimmunerkrankungen
                - Bandscheibenvorfall
                - Bauchspeicheldrüsenentzündung
                - Blutarmut
                - Blutgerinnung, Thrombose
                - Bluthochdruck
                - Bronchitis
                - Burnout
                - Candidose, Pilzinfektion
                - Chemotherapie
                - Darmentzündung, Darmbeschwerden
                - Darmflorastörung
                - Depressionen
                - Diabetes
                - Durchblutungsstörungen
                - Erkältung, Virusinfekt, Grippe
                - Erschöpfung, Müdigkeit
                - Faszien-Verklebungen
                - Fettstoffwechselstörung
                - Fibromyalgie, Faser-Muskel-Schmerz
                - Frieren, Frösteln, Kälte
                - Gastritis
                - Gehirnfunktionen
                - Gelenkschmerzen
                - Gereiztheit, Widerstand
                - Gicht
                - Grübeln, zu viel Denken
                - Haarverlust
                - Hauterkrankungen
                - Hepatitis
                - Herzinfarkt, Prophylaxe
                - Herzinsuffizienz
                - Herzkranzgefäßerkrankung
                - Herzrhythmusstörung
                - Herzunruhe, Herzrasen
                - Hörschwäche
                - Immunstärkung
                - Kalte Hände und Füße
                - Konzentrationsstörungen
                - Kopfschmerzen, Migräne
                - Krebserkrankungen
                - Leberbelastung
                - Leistungsschwäche
                - Lungenschwäche, Luftnot, flache Atmung
                - Magenschmerzen
                - Makuladegeneration
                - Muskelschwäche
                - Muskelverspannungen
                - Muskelzuckungen
                - Nachtschweiß
                - Nackenverspannungen, Nackenschmerzen
                - Potenzprobleme
                - Prostatavergrößerung
                - Rheuma
                - Rückenschmerzen
                - Schlafstörungen
                - Schlaganfall
                - Schmerzen, starke Schmerzen
                - Schwache Glieder
                - Schwindel
                - Sodbrennen
                - Taubheitsgefühle
                - Tinnitus, Ohrengeräusche
                - Unfruchtbarkeit
                - Unruhe, Stress
                - Verdauungsstörungen
                - Vergesslichkeit
                - Vergiftungen, toxische Belastungen
                - Völlegefühl
                - Wechseljahrsbeschwerden, Wechseljahrsprobleme
                - Zahnprobleme
                - Zwänge, Phobien
                You **must** extract the tags from the user message. These must be one 
                or two most related words, indicating the user's ailment, illness, diagnosis, or health complaint.
                You find tags in the examples in the square brackets.
                You **must** take one or two most related tags from the tag list above.

                Examples:
                - Was könnt ihr gegen [Ängste] empfehlen?
                - Welche Produkte helfen bei [Allergie]?
                - Ich habe Probleme mit [Augen].

                """,
            "parameters": {
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "string",
                        "description": "The tag from the list extracted from the user message",
                        "enum": [
                            "Allergien",
                            "Alterung",
                            "Angstzustände, Angst",
                            "Anspannung",
                            "Antibiotikatherapie",
                            "Antriebslosigkeit",
                            "Appetitlosigkeit",
                            "Arteriosklerose",
                            "Arthritis",
                            "Arthrose",
                            "Asthma",
                            "Augenprobleme (Sehschwäche, Rötung)",
                            "Autoimmunerkrankungen",
                            "Bandscheibenvorfall",
                            "Bauchspeicheldrüsenentzündung",
                            "Blutarmut",
                            "Blutgerinnung, Thrombose",
                            "Bluthochdruck",
                            "Bronchitis",
                            "Burnout",
                            "Candidose, Pilzinfektion",
                            "Chemotherapie",
                            "Darmentzündung, Darmbeschwerden",
                            "Darmflorastörung",
                            "Depressionen",
                            "Diabetes",
                            "Durchblutungsstörungen",
                            "Erkältung, Virusinfekt, Grippe",
                            "Erschöpfung, Müdigkeit",
                            "Faszien-Verklebungen",
                            "Fettstoffwechselstörung",
                            "Fibromyalgie, Faser-Muskel-Schmerz",
                            "Frieren, Frösteln, Kälte",
                            "Gastritis",
                            "Gehirnfunktionen",
                            "Gelenkschmerzen",
                            "Gereiztheit, Widerstand",
                            "Gicht",
                            "Grübeln, zu viel Denken",
                            "Haarverlust",
                            "Hauterkrankungen",
                            "Hepatitis",
                            "Herzinfarkt, Prophylaxe",
                            "Herzinsuffizienz",
                            "Herzkranzgefäßerkrankung",
                            "Herzrhythmusstörung",
                            "Herzunruhe, Herzrasen",
                            "Hörschwäche",
                            "Immunstärkung",
                            "Kalte Hände und Füße",
                            "Konzentrationsstörungen",
                            "Kopfschmerzen, Migräne",
                            "Krebserkrankungen",
                            "Leberbelastung",
                            "Leistungsschwäche",
                            "Lungenschwäche, Luftnot, flache Atmung",
                            "Magenschmerzen",
                            "Makuladegeneration",
                            "Muskelschwäche",
                            "Muskelverspannungen",
                            "Muskelzuckungen",
                            "Nachtschweiß",
                            "Nackenverspannungen, Nackenschmerzen",
                            "Potenzprobleme",
                            "Prostatavergrößerung",
                            "Rheuma",
                            "Rückenschmerzen",
                            "Schlafstörungen",
                            "Schlaganfall",
                            "Schmerzen, starke Schmerzen",
                            "Schwache Glieder",
                            "Schwindel",
                            "Sodbrennen",
                            "Taubheitsgefühle",
                            "Tinnitus, Ohrengeräusche",
                            "Unfruchtbarkeit",
                            "Unruhe, Stress",
                            "Verdauungsstörungen",
                            "Vergesslichkeit",
                            "Vergiftungen, toxische Belastungen",
                            "Völlegefühl",
                            "Wechseljahrsbeschwerden, Wechseljahrsprobleme",
                            "Zahnprobleme",
                            "Zwänge, Phobien",
                        ],
                    },
                    "user_message": {
                        "type": "string",
                        "description": "User message",
                    },
                },
                "required": ["tags", "user_message"],
            },
        },
    },
]
