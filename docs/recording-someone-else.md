# Recording someone else

In a real EEG lab the researcher and the person being recorded are two different people. The researcher prepares the skin, places the electrodes, runs the session and the code. The participant sits still. This kit works exactly the same way.

**When to use this page**
- You can't or shouldn't wear the electrodes yourself, for example with a pacemaker or another implanted electronic device (see [safety](safety.md))
- You want a second dataset to compare with your own
- You want to practise running a session like in a lab

## Before the session

1. **Ask.** Explain what you'll do: three stickers, about 15 minutes, nothing is felt, stop any time.
2. **Screen.** Ask the participant: pacemaker or other implanted electronic device? Skin problems where the stickers go? If yes to the first, no recording without a physician's approval ([PiEEG safety](https://docs.pieeg.com/hardware/devices/pieeg-8/safety/)).
3. **Pseudonym.** Give the participant a code like `sub-02` and use only that in file names and metadata. Never a real name. Keep the list of who is who somewhere else, or nowhere.
4. **Consent.** If the data might ever leave your laptop, get written consent first, see [if you publish](#if-you-publish).
5. **Prepare the rig.** Powerbank charged and unplugged from the wall, laptop charger unplugged, `python self_test.py` passes. Run the self test before the session, never during a recording.

## During the session

You run everything, the participant only sits.

| Researcher | Participant |
|---|---|
| Wipe forehead and mastoids, place the 3 stickers ([placement](images/placement.png)) | Sits comfortably, Pi close to the head |
| Clip E1, Ref, Biasout ([wiring](images/wiring.png)) | |
| Check the signal in the dashboard: ask for 3 blinks, see 3 spikes | Blinks 3 times |
| Start recordings and call out each block | Follows the instructions |

A simple protocol, same order every time so recordings are comparable:

```bash
python record.py --subject sub-02 --seconds 60 --label rest_eyes_open
python record.py --subject sub-02 --seconds 60 --label rest_eyes_closed
python record.py --subject sub-02 --seconds 30 --label blinks_10        # 10 blinks, about every 3 s
python record.py --subject sub-02 --seconds 30 --label jaw_clench_5     # 5 clenches
```

Anything unusual (sneezed at 40 s, phone rang) goes into the sidecar: `--notes "sneezed at 40 s"`. That's exactly the metadata NWB has fields for. Stop rules are in [safety](safety.md#connection-order).

## After the session

1. Unplug the powerbank, remove the clips, peel off the stickers.
2. Check the files: `python spectrum.py recordings/*sub-02*`.
3. If the participant wants their data deleted later, delete every file with their code.

## If you publish

Recordings of other people that go anywhere public, a GitHub repository, a preprint, a portfolio for an application or a talk, need more than a pseudonym:

- **Written consent before recording.** What is recorded, what for, where it's stored, who will see it, for how long, and that they can withdraw and have it deleted at any time without giving a reason.
- **Only pseudonymised data.** `sub-02`, no names, no birth dates, no photos, no exact recording dates if they would identify someone.
- **Treat EEG as sensitive.** EEG can count as health data under the GDPR, which has stricter rules than ordinary personal data.
- **University or lab work** goes through that institution's ethics review first. Their consent form replaces the template below.
- **Never push `recordings/`.** This repository's `.gitignore` already excludes the folder. Publish only files you chose on purpose.

A minimal consent text for home experiments, adapt it to what you actually plan:

> I agree that [researcher] records my EEG with stick on electrodes on [date] for [purpose]. The data is stored under the code [sub-XX] without my name. It may be shared [where, with whom] and is kept until [date]. I can withdraw at any time without giving a reason, and then all my data is deleted. I don't have a pacemaker or other implanted electronic device.
>
> Name, date, signature

This isn't legal advice. For anything beyond a home project, ask the ethics board or data protection office of the institution involved.

## The roles in this kit

If you're the researcher and someone else wears the electrodes, every mission still works: the analysis, the NWB conversion and the datasheet mission don't care whose brain it is. Before anyone records, you can also start with **PiEEG's published example recordings**:

```bash
python get_example_data.py
```

See [Mission 0](missions.md#mission-0-real-data-first).
