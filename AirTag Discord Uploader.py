import pytz
import requests
import time
from timezonefinder import TimezoneFinder
import json
from geopy import distance
from datetime import datetime
from dateutil.tz import tzlocal


#CHANGE USERNAME#
ITEMS_FILE_PATH = "/System/Volumes/Data/Users/YOUR_NAME/Library/Caches/com.apple.findmy.fmipcore/Items.data"
#MINIMUM MILES MOVED TO SEND NEW MESSAGE
MIN_DIS_MOVED = 0.1

#SET TIMEZONE. EXAMPLE: Europe/London
TIMEZONE = "America/Los_Angeles"

#FORMAT - [LAT, LNG, DISTANCE(miles)]
FILTERED_GEOFENCE = [   
    [0.00000, 0.0000000, 2],
    [0.00000, 0.0000000, 2]
]

#AIRTAG SERIAL NUMBERS FOR SENDING MESSAGES WITH THE NAME
# FORMAT - SN : NAME
AIRTAG_SN_NAME = {
    "AIRTAG_SERIAL_NUMBER": "AIRTAG_NAME",
    "AIRTAG_SERIAL_NUMBER": "AIRTAG_NAME"
}

# https://discord.com/api/webhooks***
DISCORD_WEBHOOKS_URLS = ["URL"]


with open("last-airtag-data.json", "r") as f:
    last_airtag_data = json.loads(f.read())


def save_last_airtag_data():
    # return
    with open("last-airtag-data.json", "w") as f:
        f.write(json.dumps(last_airtag_data))


def is_location_filtred(l_lat, l_lng):
    for lat,lng,dis in FILTERED_GEOFENCE:
        if distance.distance((l_lat, l_lng), (lat, lng)).miles < dis:
            return True
    return False


def has_numbers(s):
    return any(char.isdigit() for char in s)


def get_address_string(a):
    parts = []
    if len(a["areaOfInterest"]) != 0:
        parts.append(", ".join(a["areaOfInterest"]))

    st = a.get("fullThroroughfare")
    if st:
        parts.append(st)

    # fix for villages not showing
    fal = a.get("formattedAddressLines")
    if fal:
        already_in = [
            a.get("stateCode"),
            a.get("administrativeArea"),
            a.get("country"),
            a.get("locality"),
            a.get("streetAddress"),
            a.get("streetName"),
            st,
        ]
        for x in a["areaOfInterest"]:
            already_in.append(x)
        if st:
            for t in [x.strip() for x in st.split(",") if len(x.strip()) != 0]:
                already_in.append(t)
        res = [
            txt
            for txt in fal
            if txt not in already_in and " " not in txt and not has_numbers(txt)
        ]
        if len(res) != 0:
            parts.append(res[0])
    # fix for villages not showing

    # if a.get("stateCode"):
    #     parts.append(a.get("stateCode"))

    if a.get("locality"):
        parts.append(a.get("locality"))

    if a.get("administrativeArea"):
        if a.get("administrativeArea") not in parts:
            parts.append(a.get("administrativeArea"))

    if a.get("country"):
        parts.append(a.get("country"))

    return ", ".join(parts)




def get_time_in_location(dt: datetime, lat, lng):

    tf = TimezoneFinder()
    tz_str = tf.timezone_at(lng=lng, lat=lat) if lat and lng else TIMEZONE
    if not tz_str:
        return "N/A"
    timezone = pytz.timezone(tz_str)

    localtimezone = tzlocal()

    dt = dt.replace(tzinfo=localtimezone).astimezone(timezone)
    return dt.strftime("%A, %B %-d at %I:%M %p")


def send_message(at_name, address, ts, lat, lng):
    dt = datetime.fromtimestamp(int(ts / 1000))
    local_time = get_time_in_location(dt, lat, lng)
    my_time = get_time_in_location(dt, None, None)
    final_msg = (
        f"AirTag name: {at_name}\n"
        f"Time of update: {local_time} local time\n"
        f"New location: {address}\n"
        f"https://maps.google.com/?q={lat},{lng}"
    )
    print("sending msg: \n" + final_msg)
    print()
    for webhook_url in DISCORD_WEBHOOKS_URLS:
        try:
            r = requests.post(
                webhook_url,
                json={"content": final_msg},
            )
            if not r.ok:
                print(r.content)
        except Exception as e:
            print(f"error sending discord msg for webhook {webhook_url}", e)


def get_relevent_airtags():
    with open(ITEMS_FILE_PATH, "r") as f:
        contents = json.loads(f.read())
    return [c for c in contents if c["serialNumber"] in AIRTAG_SN_NAME]


def main_loop():
    airtags = get_relevent_airtags()

    for at in airtags:
        address = at.get("address")
        location = at.get("crowdSourcedLocation")

        if not address or not location:
            continue

        if location.get("positionType") == "safeLocation":
            continue

        address_str = get_address_string(address)
        if not address_str:
            continue

        ts = location["timeStamp"]
        sn = at["serialNumber"]
        name = AIRTAG_SN_NAME[sn]
        lat, lng = location["latitude"], location["longitude"]

        if is_location_filtred(lat,lng):
            continue

        last_data = last_airtag_data.get(sn)
        if not last_data:
            last_airtag_data[sn] = {
                "lat": lat,
                "lng": lng,
                "address": address_str,
                "ts": ts,
            }
            save_last_airtag_data()
            send_message(name, address_str, ts, lat, lng)
            continue

        prev_ts = last_data.get("ts")
        if not prev_ts:
            last_airtag_data[sn]["ts"] = ts
            save_last_airtag_data()
            continue
        else:
            if prev_ts > ts:
                continue

        if (
            distance.distance((lat, lng), (last_data["lat"], last_data["lng"])).miles
            < MIN_DIS_MOVED
            and location["horizontalAccuracy"] < 300
        ):
            continue
        if address_str == last_data["address"]:
            continue

        last_airtag_data[sn] = {
            "lat": lat,
            "lng": lng,
            "address": address_str,
            "ts": ts,
        }
        save_last_airtag_data()
        send_message(name, address_str, ts, lat, lng)

    pass


while True:
    try:
        main_loop()
    except Exception as e:
        print("error in main loop ", e)
    time.sleep(5)

