"""Contemporaneous-style seed documents for epoch e2012.

Texts are original reconstructions of public-domain government releases and
wire-style summaries of widely reported H1 2012 facts. They exist so the
index is rebuildable without a multi-day Wayback crawl. Live ingest merges
on top.
"""

from __future__ import annotations

from datetime import datetime, timezone

from psbx.schemas import Document

UTC = timezone.utc


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


SEED_DOCS: list[dict] = [
    {
        "url": "https://www.bls.gov/news.release/archives/empsit_06012012.htm",
        "outlet": "U.S. Bureau of Labor Statistics",
        "published_at": "2012-06-01T08:30:00",
        "title": "The Employment Situation — May 2012",
        "source_type": "gov",
        "syndication_count": 48,
        "gdelt_mention_count": 120,
        "front_page_minutes": 180,
        "text": (
            "The unemployment rate was 8.2 percent in May, unchanged from April. "
            "Nonfarm payroll employment rose by 69,000. The labor force participation "
            "rate held at 63.8 percent. Employment in health care continued to trend up. "
            "The number of unemployed persons was 12.7 million. Among the unemployed, "
            "the number of long-term unemployed (those jobless for 27 weeks and over) "
            "was little changed. Average hourly earnings for all employees on private "
            "nonfarm payrolls rose by 2 cents. These figures are the initial print for May."
        ),
    },
    {
        "url": "https://www.federalreserve.gov/newsevents/press/monetary/20120620a.htm",
        "outlet": "Board of Governors of the Federal Reserve",
        "published_at": "2012-06-20T14:00:00",
        "title": "FOMC statement, June 20, 2012",
        "source_type": "gov",
        "syndication_count": 60,
        "gdelt_mention_count": 200,
        "front_page_minutes": 240,
        "text": (
            "The Committee agreed to continue its program to extend the average maturity "
            "of its holdings of securities as announced in June. The Committee expects "
            "to maintain a highly accommodative stance for monetary policy. In particular, "
            "it decided to keep the target range for the federal funds rate at 0 to 1/4 percent "
            "and currently anticipates that economic conditions are likely to warrant "
            "exceptionally low levels for the federal funds rate at least through late 2014. "
            "Incoming information suggests that the economy has been expanding moderately. "
            "The Committee is prepared to take further action as appropriate to promote "
            "a stronger economic recovery."
        ),
    },
    {
        "url": "https://www.congress.gov/bill/112th-congress/house-bill/4310",
        "outlet": "Congress.gov",
        "published_at": "2012-05-18T22:00:00",
        "title": "House passes H.R. 4310, NDAA for Fiscal Year 2013",
        "source_type": "gov",
        "syndication_count": 22,
        "gdelt_mention_count": 40,
        "front_page_minutes": 40,
        "text": (
            "The House of Representatives passed H.R. 4310, the National Defense "
            "Authorization Act for Fiscal Year 2013, by a recorded vote of 299-120. "
            "The bill authorizes appropriations for military activities of the Department "
            "of Defense. It now goes to the Senate. Defense authorization bills have "
            "cleared Congress in each of the past fifty years, but Senate timing remains "
            "open and amendments on detainees and Syria are expected."
        ),
    },
    {
        "url": "https://www.congress.gov/bill/112th-congress/house-bill/3523",
        "outlet": "Congress.gov",
        "published_at": "2012-04-26T21:00:00",
        "title": "House passes CISPA, H.R. 3523",
        "source_type": "gov",
        "syndication_count": 18,
        "gdelt_mention_count": 55,
        "front_page_minutes": 90,
        "text": (
            "The House passed H.R. 3523, the Cyber Intelligence Sharing and Protection Act, "
            "on April 26, 2012. The bill would permit sharing of cyber-threat information "
            "between private firms and the government. Civil-liberties groups oppose the "
            "measure. The Senate has not scheduled a companion bill. Passage in the House "
            "does not imply enactment; several cybersecurity bills have died in the Senate."
        ),
    },
    {
        "url": "https://www.congress.gov/bill/112th-congress/senate-bill/3240",
        "outlet": "Congress.gov",
        "published_at": "2012-06-21T20:00:00",
        "title": "Senate passes farm bill S. 3240",
        "source_type": "gov",
        "syndication_count": 16,
        "gdelt_mention_count": 30,
        "front_page_minutes": 50,
        "text": (
            "The Senate passed S. 3240, the Agriculture Reform, Food, and Jobs Act of 2012, "
            "on June 21. The bill would reauthorize farm programs and nutrition assistance. "
            "House Agriculture has a competing draft. Conference is not guaranteed before "
            "the current farm law's remaining provisions lapse. A five-year bill requires "
            "House floor time that leadership has not yet locked in."
        ),
    },
    {
        "url": "https://www.congress.gov/bill/112th-congress/senate-bill/1925",
        "outlet": "Congress.gov",
        "published_at": "2012-04-26T18:00:00",
        "title": "Senate passes VAWA reauthorization S. 1925",
        "source_type": "gov",
        "syndication_count": 20,
        "gdelt_mention_count": 44,
        "front_page_minutes": 70,
        "text": (
            "The Senate passed S. 1925, the Violence Against Women Reauthorization Act, "
            "on April 26, 2012. The House has not taken up the Senate text. Disputes remain "
            "over protections for Native American, LGBT, and immigrant victims. Prior VAWA "
            "reauthorizations eventually became law, but the 112th House majority has "
            "signaled it wants a narrower bill."
        ),
    },
    {
        "url": "https://www.congress.gov/bill/112th-congress/house-bill/4348",
        "outlet": "Congress.gov",
        "published_at": "2012-06-29T16:00:00",
        "title": "Surface transportation conference nears a lapse date",
        "source_type": "gov",
        "syndication_count": 25,
        "gdelt_mention_count": 38,
        "front_page_minutes": 80,
        "text": (
            "House and Senate conferees on H.R. 4348, the surface transportation "
            "reauthorization known as MAP-21, are working against a June 30 lapse in "
            "highway authority. A short-term extension remains possible. Members describe "
            "the remaining disputes as pension smoothing, project streamlining, and "
            "keystone-related riders. Enactment in July is plausible if the conference "
            "report is filed promptly."
        ),
    },
    {
        "url": "https://www.congress.gov/bill/112th-congress/senate-bill/3187",
        "outlet": "Congress.gov",
        "published_at": "2012-05-24T17:00:00",
        "title": "Senate passes FDA user-fee reauthorization S. 3187",
        "source_type": "gov",
        "syndication_count": 12,
        "gdelt_mention_count": 15,
        "front_page_minutes": 20,
        "text": (
            "The Senate passed S. 3187, the Food and Drug Administration Safety and "
            "Innovation Act, reauthorizing PDUFA user fees. The fees expire this summer "
            "if a bill is not enacted. House passage is widely expected because industry "
            "and the administration both support the package. This is treated as must-pass "
            "legislation for 2012."
        ),
    },
    {
        "url": "https://www.congress.gov/bill/112th-congress/house-bill/5652",
        "outlet": "Congress.gov",
        "published_at": "2012-05-10T21:30:00",
        "title": "House passes Sequester Replacement Reconciliation Act",
        "source_type": "gov",
        "syndication_count": 14,
        "gdelt_mention_count": 22,
        "front_page_minutes": 35,
        "text": (
            "The House passed H.R. 5652, the Sequester Replacement Reconciliation Act of 2012, "
            "on May 10. The bill would replace the defense sequester with cuts to domestic "
            "programs. The Senate majority has said it will not take up the bill. Under "
            "divided government, House-only reconciliation substitutes rarely become law."
        ),
    },
    {
        "url": "https://www.congress.gov/bill/112th-congress/house-bill/3261",
        "outlet": "Congress.gov",
        "published_at": "2012-01-20T15:00:00",
        "title": "House postpones SOPA markup after protests",
        "source_type": "gov",
        "syndication_count": 40,
        "gdelt_mention_count": 90,
        "front_page_minutes": 200,
        "text": (
            "House Judiciary postponed markup of H.R. 3261, the Stop Online Piracy Act, "
            "after coordinated online protests. Several original cosponsors withdrew. "
            "Leadership has not rescheduled the bill. Prospects for enactment in this "
            "Congress are now remote."
        ),
    },
    {
        "url": "https://www.whitehouse.gov/the-press-office/2012/06/01/statement-fiscal-cliff",
        "outlet": "The White House",
        "published_at": "2012-06-01T12:00:00",
        "title": "Administration on year-end tax rates and sequestration",
        "source_type": "gov",
        "syndication_count": 30,
        "gdelt_mention_count": 70,
        "front_page_minutes": 100,
        "text": (
            "The administration reiterated that income-tax rates for households below "
            "$250,000 should be extended and that rates for higher-income households "
            "should return to Clinton-era levels on January 1, 2013. Sequestration under "
            "the Budget Control Act remains current law after the joint committee failed. "
            "A year-end negotiation is expected. Whether sequestration begins on January 2 "
            "depends on legislation that does not yet exist."
        ),
    },
    {
        "url": "https://www.cbo.gov/publication/43234",
        "outlet": "Congressional Budget Office",
        "published_at": "2012-05-22T14:00:00",
        "title": "CBO: Economic effects of reducing the fiscal restraint in 2013",
        "source_type": "gov",
        "syndication_count": 18,
        "gdelt_mention_count": 25,
        "front_page_minutes": 40,
        "text": (
            "CBO estimates that under current law, a combination of expiring tax provisions "
            "and automatic spending reductions will impose substantial fiscal restraint in "
            "calendar year 2013. The agency's baseline assumes sequestration occurs unless "
            "Congress changes the law. CBO does not assign a probability to legislative "
            "delay, but notes that lawmakers have previously postponed similar deadlines."
        ),
    },
    {
        "url": "https://www.state.gov/r/pa/prs/ps/2012/06/syria-annan.htm",
        "outlet": "U.S. Department of State",
        "published_at": "2012-06-12T10:00:00",
        "title": "Briefing on the Annan six-point plan and Syria",
        "source_type": "gov",
        "syndication_count": 28,
        "gdelt_mention_count": 110,
        "front_page_minutes": 85,
        "text": (
            "The Department said the Annan six-point plan has not produced a sustained "
            "ceasefire. Violence in Homs and near the Turkish border continues. Russia and "
            "China remain opposed to a Chapter VII use-of-force resolution. Assad remains "
            "in office. Officials declined to predict a timeline for a political transition."
        ),
    },
    {
        "url": "https://www.un.org/sg/en/content/sg/statement/2012-06-07/syria",
        "outlet": "United Nations",
        "published_at": "2012-06-07T09:00:00",
        "title": "Secretary-General on Syria and the Security Council",
        "source_type": "gov",
        "syndication_count": 24,
        "gdelt_mention_count": 95,
        "front_page_minutes": 60,
        "text": (
            "The Secretary-General urged the Security Council to unite behind the Annan "
            "plan. He noted that drafts authorizing military force lack nine votes and "
            "would face a veto. A nationwide ceasefire has not taken hold. Humanitarian "
            "access remains uneven."
        ),
    },
    {
        "url": "https://www.bbc.co.uk/news/world-europe-18486936",
        "outlet": "BBC News",
        "published_at": "2012-06-18T07:00:00",
        "title": "New Democracy wins Greek repeat election",
        "source_type": "news",
        "syndication_count": 55,
        "gdelt_mention_count": 300,
        "front_page_minutes": 300,
        "text": (
            "Greece's New Democracy party finished first in the June 17 repeat election, "
            "ahead of Syriza. A pro-bailout coalition is expected. Markets treated the "
            "result as reducing the near-term chance of an immediate euro exit, though "
            "debt dynamics remain severe. European officials said Greece remaining in "
            "the euro area is still the working assumption, not a certainty over a "
            "twelve-month horizon."
        ),
    },
    {
        "url": "https://www.reuters.com/article/us-iran-nuclear-moscow-idUSBRE85K0D20120619",
        "outlet": "Reuters",
        "published_at": "2012-06-19T16:00:00",
        "title": "Moscow nuclear talks with Iran end without agreement",
        "source_type": "wire",
        "syndication_count": 42,
        "gdelt_mention_count": 80,
        "front_page_minutes": 70,
        "text": (
            "P5+1 talks with Iran in Moscow ended without an agreement. The parties "
            "agreed only to expert-level follow-up. Western diplomats said a comprehensive "
            "deal this year is unlikely. Israel continues to say all options remain on "
            "the table, while U.S. officials publicly discourage a unilateral strike "
            "on Iranian nuclear facilities in the near term."
        ),
    },
    {
        "url": "https://www.reuters.com/article/us-egypt-election-idUSBRE85N0F20120624",
        "outlet": "Reuters",
        "published_at": "2012-06-24T12:00:00",
        "title": "Morsi declared winner of Egypt's presidential election",
        "source_type": "wire",
        "syndication_count": 50,
        "gdelt_mention_count": 210,
        "front_page_minutes": 220,
        "text": (
            "Mohamed Morsi of the Muslim Brotherhood was declared the winner of Egypt's "
            "presidential runoff. The Supreme Council of the Armed Forces has issued "
            "an interim constitutional declaration limiting presidential powers. Morsi "
            "is expected to take office. Whether he remains in office through mid-2013 "
            "depends on an unresolved contest with the military and a polarized street."
        ),
    },
    {
        "url": "https://www.nytimes.com/2012/06/01/world/asia/north-korea-nuclear.html",
        "outlet": "The New York Times",
        "published_at": "2012-04-13T08:00:00",
        "title": "North Korea's rocket launch fails; nuclear test watch continues",
        "source_type": "news",
        "syndication_count": 33,
        "gdelt_mention_count": 60,
        "front_page_minutes": 110,
        "text": (
            "A North Korean satellite launch in April failed shortly after liftoff. "
            "The United States called the launch a ballistic-missile test in violation "
            "of Security Council resolutions. After previous failed launches, the DPRK "
            "has sometimes followed with an underground nuclear test, as in 2009. "
            "Intelligence officials say another test in the coming year is possible "
            "but not certain."
        ),
    },
    {
        "url": "https://www.ft.com/content/china-leadership-2012-06",
        "outlet": "Financial Times",
        "published_at": "2012-06-05T05:00:00",
        "title": "Xi Jinping still seen as heir at 18th Party Congress",
        "source_type": "news",
        "syndication_count": 15,
        "gdelt_mention_count": 28,
        "front_page_minutes": 45,
        "text": (
            "Despite a brief unexplained absence in September 2012 being months away, "
            "as of June 2012 Xi Jinping remains the consensus choice to become General "
            "Secretary at the 18th Party Congress this autumn. A leadership transition "
            "is scheduled. Analysts assign a high probability that Xi takes the top "
            "party post before mid-2013, while warning that elite politics can still surprise."
        ),
    },
    {
        "url": "https://www.imf.org/external/np/sec/pr/2012/pr12245.htm",
        "outlet": "United Nations",
        "published_at": "2012-06-11T11:00:00",
        "title": "IMF staff discussions with Egypt continue",
        "source_type": "gov",
        "syndication_count": 8,
        "gdelt_mention_count": 12,
        "front_page_minutes": 10,
        "text": (
            "IMF staff held discussions with Egyptian authorities on a possible stand-by "
            "arrangement. No staff-level agreement was announced. Reserves have declined. "
            "A program would require political consensus on subsidy reform that the "
            "incoming president has not yet demonstrated."
        ),
    },
    {
        "url": "https://www.un.org/press/en/2012/sc10600.doc.htm",
        "outlet": "United Nations",
        "published_at": "2012-06-20T18:00:00",
        "title": "Security Council discusses Mali after Tuareg and Islamist advances",
        "source_type": "gov",
        "syndication_count": 10,
        "gdelt_mention_count": 18,
        "front_page_minutes": 15,
        "text": (
            "The Security Council condemned the seizure of northern Mali. ECOWAS has "
            "discussed a stabilization force. No authorization for a French-led combat "
            "intervention has been adopted. Diplomats said any international military "
            "operation would take months to assemble if it happens at all."
        ),
    },
    {
        "url": "https://www.politico.com/story/2012/06/immigration-outlook-2013",
        "outlet": "Politico",
        "published_at": "2012-06-15T13:00:00",
        "title": "Comprehensive immigration still a long shot this Congress",
        "source_type": "news",
        "syndication_count": 9,
        "gdelt_mention_count": 14,
        "front_page_minutes": 25,
        "text": (
            "The White House deferred-action announcement for some childhood arrivals "
            "does not substitute for legislation. Senate Democrats lack the votes for "
            "a comprehensive bill in the 112th Congress. A 2013 attempt would require "
            "a different Senate math after the November elections. Enactment of a full "
            "overhaul by mid-2013 remains a low-probability outcome; Senate passage of "
            "something large is a higher-probability but still uncertain outcome."
        ),
    },
    {
        "url": "https://www.thehill.com/policy/finance/cordray-cfpb-2012-06",
        "outlet": "The Hill",
        "published_at": "2012-06-08T09:30:00",
        "title": "Cordray confirmation still blocked",
        "source_type": "trade",
        "syndication_count": 6,
        "gdelt_mention_count": 8,
        "front_page_minutes": 12,
        "text": (
            "Richard Cordray continues to serve as CFPB director under a recess appointment. "
            "Republican senators say they will not confirm a director until the bureau's "
            "structure is changed. A cloture vote has not been scheduled. Confirmation "
            "before mid-2013 is possible only if the election changes Senate incentives."
        ),
    },
    {
        "url": "https://www.rollcall.com/2012/06/disabilities-treaty",
        "outlet": "Roll Call",
        "published_at": "2012-05-30T11:00:00",
        "title": "Disabilities treaty faces an uncertain Senate",
        "source_type": "trade",
        "syndication_count": 5,
        "gdelt_mention_count": 7,
        "front_page_minutes": 8,
        "text": (
            "The Convention on the Rights of Persons with Disabilities has bipartisan "
            "sponsors but also a bloc of senators who argue it would infringe U.S. "
            "sovereignty. Treaty ratification requires a two-thirds vote. Supporters "
            "hope for a lame-duck vote. Failure is a realistic outcome."
        ),
    },
    {
        "url": "https://www.bls.gov/news.release/archives/cpi_06142012.htm",
        "outlet": "U.S. Bureau of Labor Statistics",
        "published_at": "2012-06-14T08:30:00",
        "title": "Consumer Price Index — May 2012",
        "source_type": "gov",
        "syndication_count": 36,
        "gdelt_mention_count": 40,
        "front_page_minutes": 60,
        "text": (
            "The Consumer Price Index for All Urban Consumers fell 0.3 percent in May "
            "on a seasonally adjusted basis. Over the last 12 months, the all-items index "
            "increased 1.7 percent before seasonal adjustment. Energy prices declined. "
            "Forecasters expect inflation to remain moderate through year-end, which "
            "also shapes the 10-year Treasury yield outlook."
        ),
    },
    {
        "url": "https://www.census.gov/construction/nrc/pdf/newresconst.pdf",
        "outlet": "U.S. Bureau of Labor Statistics",
        "published_at": "2012-06-19T08:30:00",
        "title": "New residential construction, May 2012",
        "source_type": "gov",
        "syndication_count": 11,
        "gdelt_mention_count": 9,
        "front_page_minutes": 15,
        "text": (
            "Privately owned housing starts in May were at a seasonally adjusted annual "
            "rate of 708,000. Building permits were 780,000. Starts remain far below "
            "pre-crisis levels but have trended up from 2011. A print above 740,000 in "
            "coming months would be an upside surprise relative to the recent pace."
        ),
    },
    {
        "url": "https://www.treasury.gov/resource-center/data-chart-center/interest-rates/",
        "outlet": "Board of Governors of the Federal Reserve",
        "published_at": "2012-06-29T21:00:00",
        "title": "Treasury 10-year yield remains near historic lows",
        "source_type": "gov",
        "syndication_count": 19,
        "gdelt_mention_count": 20,
        "front_page_minutes": 30,
        "text": (
            "The 10-year Treasury yield hovered near 1.6 percent at the end of June 2012 "
            "as investors sought safety amid European stress. A move above 1.8 percent "
            "in the autumn would require either stronger U.S. data or a clear reduction "
            "in euro-area tail risk. Operation Twist continues to pin down longer rates."
        ),
    },
    {
        "url": "https://www.ecb.europa.eu/press/pr/date/2012/html/pr120606.en.html",
        "outlet": "Financial Times",
        "published_at": "2012-06-06T13:00:00",
        "title": "No euro-area enlargement scheduled for 2012-2013",
        "source_type": "news",
        "syndication_count": 7,
        "gdelt_mention_count": 6,
        "front_page_minutes": 10,
        "text": (
            "Latvia and other convergence candidates remain years from adoption. Officials "
            "said there is no plan to admit a new euro-area member in 2012 or the first "
            "half of 2013. Enlargement is not on the crisis agenda."
        ),
    },
    {
        "url": "https://www.oilandgasjournal.com/2012/06/iran-israel",
        "outlet": "Oil & Gas Journal",
        "published_at": "2012-06-22T08:00:00",
        "title": "Markets still price a low probability of an Israel-Iran strike this year",
        "source_type": "trade",
        "syndication_count": 4,
        "gdelt_mention_count": 5,
        "front_page_minutes": 5,
        "text": (
            "Crude prices reflect a modest geopolitical premium. Traders surveyed by "
            "the journal assigned a low probability to an overt Israeli strike on "
            "Iranian nuclear sites before mid-2013, citing U.S. opposition and "
            "incomplete Iranian enrichment breakout. A strike remains a tail risk "
            "that would spike oil immediately."
        ),
    },
    {
        "url": "https://www.washingtonpost.com/world/middle-east/assad-2012-06",
        "outlet": "The Washington Post",
        "published_at": "2012-06-10T19:00:00",
        "title": "Assad's forces hold Damascus as conflict militarizes",
        "source_type": "news",
        "syndication_count": 27,
        "gdelt_mention_count": 88,
        "front_page_minutes": 95,
        "text": (
            "Government forces still control Damascus and most provincial capitals. "
            "Defections continue but have not produced a collapse of the officer corps. "
            "Independent analysts split on whether Assad will still hold the presidency "
            "a year from now; the modal view is that he survives in a rump state rather "
            "than falling quickly."
        ),
    },
]


def seed_documents() -> list[Document]:
    from psbx.corpus.normalize import document_id_for

    docs: list[Document] = []
    for raw in SEED_DOCS:
        text = raw["text"]
        docs.append(
            Document(
                id=document_id_for(text),
                url=raw["url"],
                outlet=raw["outlet"],
                published_at=_dt(raw["published_at"]),
                title=raw["title"],
                text=text,
                source_type=raw["source_type"],
                prominence=0.0,
                syndication_count=int(raw["syndication_count"]),
                gdelt_mention_count=int(raw["gdelt_mention_count"]),
                front_page_minutes=float(raw["front_page_minutes"]),
                provenance=(
                    "Original reconstruction for offline practice; the URL is a subject "
                    "reference and does not authenticate this text."
                ),
                authenticity="reconstructed_fixture",
                timestamp_basis="fixture_as_of",
            )
        )
    return docs
