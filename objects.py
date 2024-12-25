from pydantic import BaseModel
from typing import List, Optional, Union, Tuple, Dict
from pathlib import Path
import logging
from enum import IntEnum
from tqdm import tqdm
from math import hypot
import shapefile
from shapely import Polygon


from leveelogic.objects.levee import Levee
from leveelogic.objects.soilprofile import (
    SoilProfile as LLSoilProfile,
    SoilLayer as LLSoilLayer,
)
from leveelogic.objects.soil import Soil as LLSoil
from leveelogic.objects.crosssection import Crosssection as LLCrosssection
from leveelogic.helpers import polyline_polyline_intersections


X_UNDEFINED = -9999

# de freatische lijn raakt de dijk, dit wordt het tweede punt van de freatische lijn
# de volgende offset bepaalt de afstand tussen het toetspeil en de z coordinaat
# van het derde punt dat komt te liggen op (x_buitenkruin, toetspeil - Z_OFFSET_BUITENKRUIN)
# Let op dat het vierde punt op toetspeil - verschil (uit DAM invoer) komt te liggen
# dus deze waarde moet groter zijn dan Z_OFFSET_BUITENKRUIN anders loopt de freatische lijn weer omhoog
Z_OFFSET_BUITENKRUIN = 0.0
# Hou altijd de volgende afstand tussen maaiveld en de freatische lijn
Z_PHREATIC_OFFSET_MAAIVELD = 0.1


def z_at(x: float, points: List[Tuple[float, float]]) -> Optional[float]:
    for i in range(1, len(points)):
        p1 = points[i - 1]
        p2 = points[i]

        if p1[0] <= x and x <= p2[0]:
            return p1[1] + (x - p1[0]) / (p2[0] - p1[0]) * (p2[1] - p1[1])

    return None


class CSVBasedObect(BaseModel):
    columns: List[str] = []
    data: List[List[str]] = []

    @classmethod
    def read(cls, filename: str) -> "CSVBasedObect":
        result = CSVBasedObect()
        lines = open(filename, "r").readlines()
        result.columns = [s.strip().replace(" ", "_") for s in lines[0].split(";")]

        for line in [l for l in lines[1:] if len(l.strip()) > 0]:
            result.data.append([s.strip() for s in line.split(";")])

        return result

    @property
    def length(self) -> int:
        return len(self.data)

    def column(self, header) -> Optional[List[str]]:
        i = self.columns.index(header)
        if i < 0:
            return None
        return [d[i] for d in self.data]

    def column_index(self, header) -> Optional[int]:
        i = self.columns.index(header)
        if i < 0:
            return None
        else:
            return i


class Soil(BaseModel):
    name: str
    yd: float
    ys: float
    c: float
    phi: float


class Combination(BaseModel):
    soilprofile_id_crest: str = ""
    soilprofile_id_toe: str = ""
    surfaceline_id: str = ""
    soilgeometry2D_name: str = ""


class SlopeLayer(BaseModel):
    surfaceline_id: str = ""
    slope_layer_thickness: float


class SoilProfileLayer(BaseModel):
    top: float
    bottom: float
    soil_name: str


class SoilProfile(BaseModel):
    id: str
    layers: List[SoilProfileLayer] = []

    def sort(self) -> None:
        self.layers = sorted(self.layers, key=lambda x: x.top, reverse=True)


class PolderPeil(BaseModel):
    location_id: str
    max_peil: float
    min_peil: float


class Stijghoogte(BaseModel):
    location_id: str
    hoogte: float


class Toetspeil(BaseModel):
    location_id: str
    peil: float
    verschil: float


class SurfaceLinePoint(BaseModel):
    x: float
    y: float
    z: float

    def as_2d(
        self, start_point: Optional["SurfaceLinePoint"] = None
    ) -> Tuple[float, float]:  # TODO dit werkt niet voor 3D punten
        """Return this point as a x,z 2D point

        Args:
            start_point (Optional[SurfaceLinePoint], if set this will be used to calculate the x
            value as the distance between the startpoint and this point. Note that this will always
            result in a positive value so the startpoint has to be at the beginning or end of a line

        Returns:
            Tuple[float, float]: Tuple of x,z coordinates
        """
        if start_point is not None:
            return (hypot(start_point.x - self.x, start_point.y - self.y), self.z)
        else:
            return (self.x, self.z)


class SurfaceLine(BaseModel):
    id: str
    points: List[SurfaceLinePoint] = []

    x_binnenkruin: float = X_UNDEFINED
    x_buitenkruin: float = X_UNDEFINED
    x_binnenteen: float = X_UNDEFINED
    x_buitenteen: float = X_UNDEFINED
    x_insteek_binnenberm: float = X_UNDEFINED
    x_insteek_sloot_dijkzijde: float = X_UNDEFINED
    x_insteek_sloot_polderzijde: float = X_UNDEFINED

    @property
    def has_berm(self) -> bool:
        return self.x_insteek_binnenberm != X_UNDEFINED

    @property
    def has_sloot(self) -> bool:
        return self.x_insteek_sloot_dijkzijde != X_UNDEFINED


class Segment(BaseModel):
    pass


class Location(BaseModel):
    id: str
    surfaceline_id: str


class DAMInput(BaseModel):
    combinations: List[Combination] = []
    slopelayers: List[SlopeLayer] = []
    soilprofiles: List[SoilProfile] = []
    surfacelines: List[SurfaceLine] = []
    polderpeilen: List[PolderPeil] = []
    stijghoogtes: List[Stijghoogte] = []
    toetspeilen: List[Toetspeil] = []
    locations: List[Location] = []
    soils: List[Soil] = []

    @classmethod
    def from_folder(cls, folder: str, shapenames_dict: Dict) -> Optional["DAMInput"]:
        result = DAMInput()
        try:
            combinations = CSVBasedObect.read(Path(folder) / "combinationfile.csv")
            slopelayers = CSVBasedObect.read(Path(folder) / "slopelayers.csv")
            soilprofiles = CSVBasedObect.read(Path(folder) / "soilprofiles.csv")
            charpoints = CSVBasedObect.read(Path(folder) / "characteristicpoints.csv")
            locations = CSVBasedObect.read(Path(folder) / "locations.csv")

            ################
            # POLDERPEILEN #
            ################
            sf_polderpeilen = shapefile.Reader(
                Path(folder) / shapenames_dict["polderpeilen"]
            )
            for rec in sf_polderpeilen.records():
                result.polderpeilen.append(
                    PolderPeil(
                        location_id=rec["locationid"],
                        min_peil=rec["MIN_PEIL"],
                        max_peil=rec["MAX_PEIL"],
                    )
                )

            ###############
            # STIJGHOOGTE #
            ###############
            sf_stijghoogte = shapefile.Reader(
                Path(folder) / shapenames_dict["stijghoogte"]
            )
            for rec in sf_stijghoogte.records():
                result.stijghoogtes.append(
                    Stijghoogte(location_id=rec["locationid"], hoogte=rec["HOOGTE"])
                )

            ###############
            # TOETSPEILEN #
            ###############
            sf_toetspeilen = shapefile.Reader(
                Path(folder) / shapenames_dict["toetspeilen"]
            )
            for rec in sf_toetspeilen.records():
                result.toetspeilen.append(
                    Toetspeil(
                        location_id=rec["CODE"],
                        peil=rec["TOETSPEIL"],
                        verschil=rec["VERSCHIL"],
                    )
                )

        except Exception as e:
            raise ValueError(f"Fout bij het lezen van de invoergegevens; '{e}'")

        ###############################################
        # LOCATIONS (nodig om polderpeilen te vinden) #
        ###############################################
        for d in locations.data:
            result.locations.append(
                Location(
                    id=d[locations.column_index("location_id")],
                    surfaceline_id=d[locations.column_index("surfaceline_id")],
                )
            )

        ################
        # COMBINATIONS #
        ################
        for d in combinations.data:
            result.combinations.append(
                Combination(
                    soilprofile_id_crest=d[
                        combinations.column_index("soilprofile_id_crest")
                    ],
                    soilprofile_id_toe=d[
                        combinations.column_index("soilprofile_id_toe")
                    ],
                    surfaceline_id=d[combinations.column_index("surfaceline_id")],
                    soilgeometry2D_name=d[
                        combinations.column_index("soilgeometry2D_name")
                    ],
                )
            )

        ################
        # SOILPROFILES #
        ################
        unique_ids = list(
            set(
                [
                    d[soilprofiles.column_index("soilprofile_id")]
                    for d in soilprofiles.data
                ]
            )
        )
        for id in unique_ids:
            soilprofile = SoilProfile(id=id)

            layers = [
                d
                for d in soilprofiles.data
                if d[soilprofiles.column_index("soilprofile_id")] == id
            ]

            for layer in layers:
                soilprofile.layers.append(
                    SoilProfileLayer(
                        top=float(layer[soilprofiles.column_index("top_level")]),
                        bottom=float(layer[soilprofiles.column_index("bottom_level")]),
                        soil_name=layer[soilprofiles.column_index("soil_name")],
                    )
                )

            # just to be sure
            soilprofile.sort()
            result.soilprofiles.append(soilprofile)

        ################
        # SURFACELINES #
        ################
        lines = open(Path(folder) / "surfacelines.csv").readlines()
        for line in lines[1:]:
            args = [s.strip() for s in line.split(";")]
            xs = [float(a) for a in args[1 : len(args) : 3]]
            ys = [float(a) for a in args[2 : len(args) : 3]]
            zs = [float(a) for a in args[3 : len(args) : 3]]

            result.surfacelines.append(
                SurfaceLine(
                    id=args[0],
                    points=[
                        SurfaceLinePoint(x=d[0], y=d[1], z=d[2])
                        for d in zip(xs, ys, zs)
                    ],
                )
            )

        #############################
        # ADD CHARACTERISTIC POINTS #
        #############################
        for d in charpoints.data:
            location_id = d[charpoints.column_index("LOCATIONID")]
            x_buitenteen = float(d[charpoints.column_index("X_Teen_dijk_buitenwaarts")])
            x_buitenkruin = float(d[charpoints.column_index("X_Kruin_buitentalud")])
            x_binnenkruin = float(d[charpoints.column_index("X_Kruin_binnentalud")])
            x_binnenteen = float(d[charpoints.column_index("X_Teen_dijk_binnenwaarts")])
            x_insteek_binnenberm = float(
                d[charpoints.column_index("X_Insteek_binnenberm")]
            )
            x_insteek_sloot_dijkzijde = float(
                d[charpoints.column_index("X_Insteek_sloot_dijkzijde")]
            )
            x_insteek_sloot_polderzijde = float(
                d[charpoints.column_index("X_Insteek_sloot_polderzijde")]
            )

            result.add_charpoints(
                location_id=location_id,
                x_buitenteen=x_buitenteen,
                x_buitenkruin=x_buitenkruin,
                x_binnenkruin=x_binnenkruin,
                x_binnenteen=x_binnenteen,
                x_insteek_binnenberm=x_insteek_binnenberm,
                x_insteek_sloot_dijkzijde=x_insteek_sloot_dijkzijde,
                x_insteek_sloot_polderzijde=x_insteek_sloot_polderzijde,
            )

        ###################
        # SOIL PARAMETERS #
        ###################
        lines = open(Path(folder) / "soilparameters.csv").readlines()
        for line in lines[1:]:
            args = [s.strip() for s in line.split(";")]
            result.soils.append(
                Soil(
                    name=args[0],
                    yd=float(args[1]),
                    ys=float(args[2]),
                    c=float(
                        args[4]
                    ),  # 4.. niet zo handig.. maar goed, csv bestand is zo opgesteld :-)
                    phi=float(args[3]),
                )
            )

        ################
        # SLOPE LAYERS #
        ################
        for d in slopelayers.data:
            result.slopelayers.append(
                SlopeLayer(
                    surfaceline_id=d[slopelayers.column_index("surfaceline_id")],
                    slope_layer_thickness=float(
                        d[slopelayers.column_index("slope_layer_thickness")]
                    ),
                )
            )

        return result

    def add_charpoints(
        self,
        location_id: str,
        x_buitenteen: float,
        x_buitenkruin: float,
        x_binnenkruin: float,
        x_insteek_binnenberm: float,
        x_binnenteen: float,
        x_insteek_sloot_dijkzijde: float,
        x_insteek_sloot_polderzijde: float,
    ) -> None:
        for i in range(len(self.surfacelines)):
            if self.surfacelines[i].id == location_id:
                self.surfacelines[i].x_binnenkruin = x_binnenkruin
                self.surfacelines[i].x_binnenteen = x_binnenteen
                self.surfacelines[i].x_buitenteen = x_buitenteen
                self.surfacelines[i].x_buitenkruin = x_buitenkruin
                if x_insteek_binnenberm != -1.0:
                    self.surfacelines[i].x_insteek_binnenberm = x_insteek_binnenberm
                if x_insteek_sloot_dijkzijde != -1.0:
                    self.surfacelines[i].x_insteek_sloot_dijkzijde = (
                        x_insteek_sloot_dijkzijde
                    )
                if x_insteek_sloot_polderzijde != -1.0:
                    self.surfacelines[i].x_insteek_sloot_polderzijde = (
                        x_insteek_sloot_polderzijde
                    )
                return

        raise ValueError(
            f"Geen karakteristieke punten gevonden voor surfaceline '{location_id}'"
        )

    def get_soilprofile(self, id: str) -> Optional[SoilProfile]:
        for sp in self.soilprofiles:
            if sp.id == id:
                return sp

        raise ValueError(f"Kan grondopbouw met id '{id}' niet vinden")

    def get_surfaceline(self, id: str) -> Optional[SurfaceLine]:
        for sl in self.surfacelines:
            if sl.id == id:
                return sl

        raise ValueError(f"Kan dwarsprofiel met id '{id}' niet vinden")

    def get_slope_layer(self, surfaceline_id: str) -> Optional[SlopeLayer]:
        for sl in self.slopelayers:
            if sl.surfaceline_id == surfaceline_id:
                return sl

        raise ValueError(f"Kan slopelayer met surfaceline_id '{id}' niet vinden")

    def get_polderpeilen(self, location_id: str) -> Optional[PolderPeil]:
        for pp in self.polderpeilen:
            if pp.location_id == location_id:
                return pp
        raise ValueError(
            f"Kan polderpeilen voor location_id '{location_id}' niet vinden"
        )

    def get_location(self, surfaceline_id: str) -> Optional[Location]:
        for l in self.locations:
            if l.surfaceline_id == surfaceline_id:
                return l

        raise ValueError(
            f"Kan location voor surfaceline_id '{surfaceline_id}' niet vinden"
        )

    def get_toetspeilen(self, location_id: str) -> Optional[Toetspeil]:
        for t in self.toetspeilen:
            if t.location_id == location_id:
                return t
        raise ValueError(
            f"Kan toetspeilen voor location_id '{location_id}' niet vinden"
        )

    def get_stijghoogte(self, location_id: str) -> Optional[Stijghoogte]:
        for s in self.stijghoogtes:
            if s.location_id == location_id:
                return s
        raise ValueError(
            f"Kan stijghoogte voor location_id '{location_id}' niet vinden"
        )

    def generate_stix_files(self, output_path: Union[str, Path]) -> None:
        Path(output_path).mkdir(parents=True, exist_ok=True)

        area_file = open(Path(output_path) / f"areas.csv", "w")
        limited_area_file = open(Path(output_path) / f"limited_areas.csv", "w")
        soilnames = [s.name for s in self.soils]
        header = "id;" + ";".join(soilnames)
        area_file.write(f"{header}\n")
        limited_area_file.write(f"{header}\n")

        # let op bij 3d punten -> nu wordt x binnenkruin, binnenteen bepaald via x,z punten bij x,y,z gaat dat fout

        for combination in tqdm(self.combinations):
            # generate filenames
            stix_filename = (
                Path(output_path) / f"{combination.soilgeometry2D_name}.stix"
            )
            log_filename = Path(output_path) / f"{combination.soilgeometry2D_name}.log"

            # get data
            try:
                crest_soilprofile = self.get_soilprofile(
                    combination.soilprofile_id_crest
                )
                polder_soilprofile = self.get_soilprofile(
                    combination.soilprofile_id_toe
                )
                surfaceline = self.get_surfaceline(combination.surfaceline_id)
                slope_layer = self.get_slope_layer(combination.surfaceline_id)
                location = self.get_location(surfaceline.id)
                polderpeilen = self.get_polderpeilen(location.id)
                toetspeil = self.get_toetspeilen(location.id)
                stijghoogte = self.get_stijghoogte(location.id)
            except Exception as e:
                logging.error(
                    f"Fout bij het afhandelen van '{combination.soilgeometry2D_name}'; '{e}'"
                )

            # write a summary of the input
            flog = open(log_filename, "w")
            flog.write("LOGFILE\n")
            flog.write(f"soilgeometry2D_name: {combination.soilgeometry2D_name}\n")
            flog.write("-----------------\n")
            flog.write("GRONDOPBOUW KRUIN\n")
            flog.write("-----------------\n")
            for l in crest_soilprofile.layers:
                flog.write(f"{l.top:8.2f},{l.bottom:8.2f}, {l.soil_name}\n")
            flog.write("----------------\n")
            flog.write("GRONDOPBOUW TEEN\n")
            flog.write("----------------\n")
            for l in polder_soilprofile.layers:
                flog.write(f"{l.top:8.2f},{l.bottom:8.2f}, {l.soil_name}\n")
            flog.write("------------\n")
            flog.write("POLDERPEILEN\n")
            flog.write("------------\n")
            flog.write(f"Minimaal  : {polderpeilen.min_peil:5.2f} [m]\n")
            flog.write(f"Maximaal  : {polderpeilen.max_peil:5.2f} [m]\n")
            flog.write("------------\n")
            flog.write("TOETSPEIL\n")
            flog.write("---------\n")
            flog.write(f"Toetspeil : {toetspeil.peil:5.2f} [m]\n")
            flog.write(f"Verschil  : {toetspeil.verschil:5.2f} [m]\n")
            flog.write("-----------\n")
            flog.write("STIJGHOOGTE\n")
            flog.write("-----------\n")
            flog.write(f"Stijghoogte : {stijghoogte.hoogte:5.2f} [m]\n")
            flog.write("-----------------------\n")
            flog.write("GRONDSOORTEN PARAMETERS\n")
            flog.write("-----------------------\n")
            flog.write("name                       yd     ys     c       phi\n")
            for s in self.soils:
                flog.write(
                    f"{s.name:25s} {s.yd:6.2f} {s.ys:6.2f} {s.c:6.2f} {s.phi:6.2f}\n"
                )
            flog.write("----------------------\n")
            flog.write("KARAKTERISTIEKE PUNTEN\n")
            flog.write("----------------------\n")
            flog.write(
                f"Xbuitenteen                : {surfaceline.x_buitenteen:5.2f} [m]\n"
            )
            flog.write(
                f"Xbuitenkruin               : {surfaceline.x_buitenkruin:5.2f} [m]\n"
            )
            flog.write(
                f"Xbinnenkruin               : {surfaceline.x_binnenkruin:5.2f} [m]\n"
            )
            if surfaceline.has_berm:
                flog.write(
                    f"Xinsteekberm               : {surfaceline.x_insteek_binnenberm:5.2f} [m]\n"
                )
            else:
                flog.write("Xinsteekberm               : Geen berm gevonden\n")
            flog.write(
                f"Xbinnenteen                : {surfaceline.x_binnenteen:5.2f} [m]\n"
            )
            if surfaceline.has_sloot:
                flog.write(
                    f"Xinsteek_sloot_dijkzijde   : {surfaceline.x_insteek_sloot_dijkzijde:5.2f} [m]\n"
                )
                if surfaceline.x_insteek_sloot_dijkzijde is not X_UNDEFINED:
                    flog.write(
                        f"Xinsteek_sloot_polderzijde : {surfaceline.x_insteek_sloot_polderzijde:5.2f} [m]\n"
                    )

            flog.write("------------\n")
            flog.write("DEKLAAG KLEI\n")
            flog.write("------------\n")
            flog.write(
                f"Kleilaag dikte: {slope_layer.slope_layer_thickness:5.2f} [m]\n"
            )

            flog.close()

            ##########################
            # GENERATE THE STIX FILE #
            ##########################
            ll_soils = [
                LLSoil(code=s.name, yd=s.yd, ys=s.ys, c=s.c, phi=s.phi, color="#000000")
                for s in self.soils
            ]
            sp_crest = LLSoilProfile(
                soillayers=[
                    LLSoilLayer(top=l.top, bottom=l.bottom, soilcode=l.soil_name)
                    for l in crest_soilprofile.layers
                ]
            )
            sp_polder = LLSoilProfile(
                soillayers=[
                    LLSoilLayer(top=l.top, bottom=l.bottom, soilcode=l.soil_name)
                    for l in polder_soilprofile.layers
                ]
            )

            crosssection = LLCrosssection(
                points=[p.as_2d() for p in surfaceline.points]
            )

            levee = Levee.from_soilprofiles(
                profile_waterside=sp_crest,
                profile_landside=sp_polder,
                crosssection=crosssection,
                x_landside=surfaceline.x_binnenteen,
                soils=ll_soils,
                fill_soilcode="Zand",
            )

            if slope_layer.slope_layer_thickness > 0:
                levee.add_toplayer(
                    x_start=surfaceline.x_binnenkruin,
                    x_end=surfaceline.x_binnenteen,
                    height=slope_layer.slope_layer_thickness,
                    soilcode="ophoogmateriaal_klei",
                )

            # P1 (links, toetspeil)
            p1 = [levee.left, toetspeil.peil]

            # P2 (eerste snijpunt met de dijk, toetspeil)
            intersections = levee.get_surface_intersections(
                points=[p1, (surfaceline.x_buitenkruin, toetspeil.peil)]
            )
            if len(intersections) == 0:
                raise ValueError(
                    "Kan geen snijpunt op het toetspeil met de dijk vinden tussen de linker limiet en de buitenkruin van dit profiel"
                )
            p2 = [intersections[0][0], toetspeil.peil]

            # P3 (buitenkruin, toetspeil minus Z_OFFSET_BUITENKRUIN) # let op dat Z_OFFSET_BUITENKRUIN < toetspeil.verschil!
            p3 = [surfaceline.x_buitenkruin, p2[1] - Z_OFFSET_BUITENKRUIN]

            # P4 = (binnenkruin, toetspeil - verschil)
            p4 = [surfaceline.x_binnenkruin, p2[1] - toetspeil.verschil]
            if p3[1] < p4[1]:
                raise ValueError(
                    "De z coordinaat van punt 3 is lager dan die van punt 4, dit kan gebeuren als `Z_OFFSET_BUITENKRUIN` groter is dan `verschil` in de DAM invoer"
                )

            # P5 = OPTIONEEL (insteek binnenberm, maaiveld - Z_PHREATIC_OFFSET_MAAIVELD)
            if surfaceline.x_insteek_binnenberm == X_UNDEFINED:
                p5 = []
            else:
                p5 = [
                    surfaceline.x_insteek_binnenberm,
                    levee.z_at(surfaceline.x_insteek_binnenberm)
                    - Z_PHREATIC_OFFSET_MAAIVELD,
                ]

            # P6 = (binnenteen, maaiveld - Z_PHREATIC_OFFSET_MAAIVELD)
            p6 = [
                surfaceline.x_binnenteen,
                levee.z_at(surfaceline.x_binnenteen) - Z_PHREATIC_OFFSET_MAAIVELD,
            ]

            # OPTIONEEL P7 = (insteek sloot polderzijde, polderpeil max peil)
            # P8 indien sloot (rechter limiet, polderpeil max peil)
            # P8 geen sloot (rechter limiet, maaiveld - Z_PHREATIC_OFFSET_MAAIVELD)
            if surfaceline.has_sloot:
                p7 = [surfaceline.x_insteek_sloot_dijkzijde, polderpeilen.min_peil]
                p8 = [levee.right, polderpeilen.min_peil]
            else:
                p7 = []
                p8 = [levee.right, levee.z_at(levee.right) - Z_PHREATIC_OFFSET_MAAIVELD]

            # genereer de punten en discard de lege punten
            pl_points = [p for p in [p1, p2, p3, p4, p5, p6, p7, p8] if len(p) != 0]

            if surfaceline.x_insteek_binnenberm != X_UNDEFINED:
                xl = surfaceline.x_insteek_binnenberm
            else:
                xl = surfaceline.x_binnenkruin

            if surfaceline.has_sloot:
                xr = surfaceline.x_insteek_sloot_dijkzijde
            else:
                xr = levee.right

            xs = [p[0] for p in levee.surface if p[0] > xl and p[0] <= xr]
            xs += [p[0] for p in pl_points if p[0] > xl and p[0] <= xr]
            xs = sorted(list(set(xs)))

            # maak de nieuwe pl lijn
            # voeg eerst de punten tot en met de binnenkruin toe
            final_pl_points = [
                p for p in pl_points if p[0] <= surfaceline.x_binnenkruin
            ]

            # voeg alle punten tussen xl en xr toe en check de hoogte tov mv
            for x in xs:
                z_mv = levee.z_at(x)
                z_pl = z_at(x, pl_points)
                if z_pl > z_mv - Z_PHREATIC_OFFSET_MAAIVELD:
                    final_pl_points.append([x, z_mv - Z_PHREATIC_OFFSET_MAAIVELD])
                else:
                    final_pl_points.append([x, z_pl])

            # als xr != levee.right voeg ook dan nog de oude punten toe
            if xr != levee.right:
                final_pl_points += [p for p in pl_points if p[0] > xr]

            # en zorg ervoor dat de punten aflopend zijn
            for i in range(1, len(final_pl_points)):
                if final_pl_points[i - 1][1] < final_pl_points[i][1]:
                    final_pl_points[i][1] = final_pl_points[i - 1][1]

            # voeg de pl lijn toe
            levee.add_phreatic_line(points=final_pl_points)

            areas = {s: 0.0 for s in soilnames}
            limited_areas = {s: 0.0 for s in soilnames}

            left_subtract = Polygon(
                [
                    (levee.left - 1.0, levee.top + 1.0),
                    (surfaceline.x_buitenteen, levee.top + 1.0),
                    (surfaceline.x_buitenteen, levee.bottom - 1.0),
                    (levee.left - 1.0, levee.bottom - 1.0),
                    (levee.left - 1.0, levee.top + 1.0),
                ]
            )
            right_subtract = Polygon(
                [
                    (surfaceline.x_binnenteen, levee.top + 1.0),
                    (levee.right + 1.0, levee.top + 1.0),
                    (levee.right + 1.0, levee.bottom - 1.0),
                    (surfaceline.x_binnenteen, levee.bottom - 1.0),
                    (surfaceline.x_binnenteen, levee.top + 1.0),
                ]
            )
            bottom_subtract = Polygon(
                [
                    (levee.left - 1.0, polderpeilen.min_peil),
                    (levee.right + 1.0, polderpeilen.min_peil),
                    (levee.right + 1.0, levee.bottom - 1.0),
                    (levee.left - 1.0, levee.bottom - 1.0),
                    (levee.left - 1.0, polderpeilen.min_peil),
                ]
            )

            for spg in levee.soilpolygons:
                areas[spg.soilcode] += spg.to_shapely().area

                # limit to binnen- en buitenteen en minimaal polderpeil
                pg = spg.to_shapely()

                if pg.intersects(left_subtract):
                    pg = pg.difference(left_subtract)
                if pg.intersects(right_subtract):
                    pg = pg.difference(right_subtract)
                if pg.intersects(bottom_subtract):
                    pg = pg.difference(bottom_subtract)

                limited_areas[spg.soilcode] += pg.area

            s = f"{combination.soilgeometry2D_name};"
            s_limited = f"{combination.soilgeometry2D_name};"
            for soilname in soilnames:
                s += f"{areas[soilname]:.2f};"
                s_limited += f"{limited_areas[soilname]:.2f};"
            s = s[:-1] + "\n"
            s_limited = s_limited[:-1] + "\n"
            area_file.write(s)
            limited_area_file.write(s_limited)

            levee.to_stix(stix_filename)

        area_file.close()
        limited_area_file.close()
